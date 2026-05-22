# FastGPT 源码分析（对标 Chameleon）

## 1. 架构总览

FastGPT 采用 **Next.js + Mongoose + PostgreSQL（pgvector）+ MinIO** 的现代化 RAG 架构。核心设计分为三层：

### 1.1 数据模型层（Mongoose Schemas）
- **Dataset** 和 **DatasetCollection** 为树状结构（支持文件夹），允许多级组织
  - `packages/service/core/dataset/schema.ts` (L59-100)：Dataset 记录 vectorModel、agentModel、chunkSettings 等全局配置
  - `packages/service/core/dataset/collection/schema.ts` (L14-88)：Collection 支持 file/link/folder/apiFile/images 多种类型，包含 fileId（MinIO）、customPdfParse、chunkSettings 等
  
- **DatasetData**（chunk 记录）：一对多关系到 Collection
  - `packages/service/core/dataset/data/schema.ts` (L15-100)：包含 q/a（问答对）、imageId、indexes 数组（支持多索引）、chunkIndex（chunk序号）
  - 核心字段：`indexes[].type`（DatasetDataIndexTypeEnum.custom|search）+ `indexes[].text`（存储内容）

- **DatasetTraining**（待处理任务队列）：异步处理管道
  - `packages/service/core/dataset/training/schema.ts` (L18-120)：记录 mode（parse/chunk/qa/image）、retryCount、错误信息、billId 计费关联

### 1.2 文件处理 Pipeline
```
上传 → S3 存储 → Collection 创建 → 推送解析任务 → Training 队列处理 
  → 生成 DatasetData → Vector DB + 全文索引
```

具体流程（`projects/app/src/pages/api/core/dataset/collection/create/localFile.ts` L17-73）：
1. **上传**：multer 接收表单数据，检查文件大小和扩展名
2. **存储**：上传到 MinIO（getS3DatasetSource），获取 fileId
3. **创建 Collection**：保存元数据（customPdfParse、chunkSettings）到 MongoDB
4. **推送任务**：`createCollectionAndInsertData()` 触发 BullMQ 队列

### 1.3 向量检索架构
- **embedding recall**：pgvector cosine 相似度
- **full-text recall**：PostgreSQL tsvector（jieba 中文分词）
- **RRF 融合**：倒数排名融合（Reciprocal Rank Fusion）
- **rerank 可选**：接入第三方 rerank 模型（如 bge-reranker）
- **图片检索**：VLM caption 生成 → 作为文本 query 参与检索；如果 embedding 模型支持图片，另走图像向量召回

---

## 2. Top 5 RAG/KB 杀手级特性（按对 Chameleon 启发排序）

### 特性 1：多模式分块策略系统（最高优先级）
**问题**：Chameleon 当前仅按字符切 → 无法处理复杂文档结构

**FastGPT 解决方案**：
- **策略枚举**（`packages/global/core/dataset/constants.ts` L215-224）：
  - `DataChunkSplitModeEnum`：paragraph（按段）、size（按字符）、char（单字符）
  - `ChunkTriggerConfigTypeEnum`：minSize、forceChunk、maxSize（触发条件）
  - `ParagraphChunkAIModeEnum`：auto/force/forbid（段落检测是否用 AI）

- **实现细节**：
  - Collection 级别配置：`chunkSize`、`chunkSplitter`、`paragraphChunkDeep`、`paragraphChunkMinSize`
  - 支持自定义分隔符和递归分割深度
  - Token 级分块：通过 `getLLMMaxChunkSize()` 计算 LLM token 上限，自动调整 chunk 大小

- **跨项目对照**：
  - RAGFlow 的 `token_chunker.py` 支持 token 计数 + 重叠配置（overlap_percent）
  - RAGFlow `title_chunker` 支持按标题层级递归分组

**启发**：建议 Chameleon 迁移到 token-based chunking + 可视化分块策略编辑器

---

### 特性 2：分层式知识库 + 应用组织模型
**关键优势**：FastGPT 把知识库视为 RAG 资源池，可被多个应用（Workflow）复用

**数据关系**（`packages/service/core/dataset/schema.ts` + collection/schema.ts）：
```
Dataset (知识库) 
  ├─ Collection (文件/链接/API 数据源) [多个]
  │   ├─ DatasetData (chunk) [多个]
  │   │   └─ indexes[] (多索引支持)
  │   └─ DatasetTraining (任务队列)
  └─ chunkSettings (全局分块策略)
```

**应用层使用**：Workflow 的 `datasetSearchNode` 节点引用 Dataset，触发 `searchDatasetData()`
  - `packages/service/core/workflow/dispatch/dataset/nodeResponse.ts`：datasetSearchNode 支持 query extension、image caption、rerank 等子节点
  - 完整计费链路：每次查询生成 usage 记录，包括 embedding tokens、rerank tokens、VLM caption tokens

**启发**：建议 Chameleon 实现 KB 级的 chunk/embedding 统计仪表板；引入"应用"概念，允许跨 KB 搜索

---

### 特性 3：富媒体优先的 Collection 类型系统
**FastGPT 支持的 Collection 类型**（`packages/global/core/dataset/constants.ts` L116-148）：
- `file`：本地上传（PDF/Word/Markdown 等）
- `link`：单个网页 URL
- `apiFile`：第三方 API 数据源（Feishu、Yuque、DingTalk）
- `images`：图片集合 + image description
- `folder` 和 `virtual`：逻辑组织

**每种类型的处理模式**（DatasetCollectionDataProcessModeEnum，L167-203）：
- `chunk`：文本切分 → embedding
- `qa`：问答对直接导入
- `imageParse`：图片 → VLM 描述 → embedding
- `backup`、`template`：无需处理的备份/模板数据

**启发**：Chameleon 可以扩展支持网页抓取（selector-based）、API 数据源同步、图片描述生成

---

### 特性 4：搜索测试与可视化 + hit-test UI
**测试流程**（前端：`projects/app/src/pageComponents/dataset/detail/Test/`）：
1. 上传测试图片或文本query
2. 调用 `getPreviewChunks()` API（`projects/app/src/web/core/dataset/api/file.ts` L16-20）
3. 实时返回：
   - 匹配的 chunks（包含 dataId、text、score）
   - 搜索得分来源（embedding/fulltext/rerank/rrf）
   - 文件位置高亮

**关键 API**：
- `POST /core/dataset/file/getPreviewChunks`：返回 chunks + hit 分数
- `POST /core/dataset/file/getSearchTestImagePreviewUrls`：图片预览 URL 生成

**启发**：Chameleon 前端 `/kbs` 可以添加"search playground"模块，实时展示 chunks + 高亮位置

---

### 特性 5：Workflow 节点化知识库调用 + 完整追溯链路
**设计亮点**：知识库不仅是数据源，而是 Workflow DAG 中的一级节点

**节点类型**（`packages/global/core/workflow/type/node.ts`）：
- `datasetSearchNode`：包含内部 LLM 处理（query extension、image caption、rerank）
- 响应结构 (`nodeResponse.ts` L9-111)：
  ```typescript
  ChatHistoryItemResType {
    nodeId, moduleName, runningTime,
    inputTokens, outputTokens, totalPoints,
    llmRequestIds[], textOutput
  }
  ```

**多级子处理**：
- Query Extension：LLM 扩展原始问题 → 多路召回
- Image Caption：VLM 把图片转成文本描述
- Chunk Selection：当返回过长，LLM 精选重要 chunks
- Rerank：向量召回后用 rerank 模型精排

**启发**：Chameleon 可以参考这种"节点追溯"设计，在 embedding 结果中记录：
- 使用的分块策略版本
- embedding 模型名称
- 搜索参数（top-k、相似度阈值）
- 每个 chunk 的得分来源（向量 vs 全文）

---

## 3. 三个值得借鉴的实现模式

### 模式 1：BullMQ 异步任务队列 + Collection 更新防抖
**文件**：`packages/service/core/dataset/collection/mq.ts`

**实现**：
- 集合更新任务（updateTime、统计数据）通过 BullMQ 去重
- 任务 ID = `collection-update-${collectionId}`，确保同一 collection 只排队一次
- 延迟 5 秒执行，避免频繁更新数据库
- 并发数控制：`concurrency: 3`

```typescript
// 失败重试策略
const jobId = `collection-update-${data.collectionId}`;
await queue.add('updateCollection', data, {
  jobId,  // 防抖
  delay: 5000  // 延迟执行
});
```

**Chameleon 参考**：
- 表：`knowledge_collection` 新增 `update_queue_status` 字段跟踪任务状态
- API：`PATCH /knowledge/{kb_id}/collection/{col_id}/sync-metadata`
- 处理：统一通过 Celery 任务队列，记录最近一次更新时间

---

### 模式 2：多索引字段设计（indexes 数组）
**文件**：`packages/service/core/dataset/data/schema.ts` L51-74

**数据结构**：
```javascript
indexes: [
  { 
    type: 'custom' | 'search',  // 索引类型
    dataId: String,  // 向量库中的 ID
    text: String  // 实际检索内容
  }
]
```

**优势**：
1. 支持一个 chunk 生成多个索引（如原文 + 摘要 + QA 对）
2. 灵活的索引类型扩展（保留 custom、search 以外的类型空间）
3. 便于后续添加图文索引、表格索引等

**Chameleon 参考**：
- 表 schema：chunks 新增 `indexes JSONB[]` 字段
- SQL 结构：
  ```sql
  CREATE TABLE chunks (
    id UUID PRIMARY KEY,
    collection_id UUID,
    text TEXT,
    indexes JSONB[] DEFAULT '{}',  -- [{type: 'chunk', embedding_id: ...}, {type: 'qa', q: ..., a: ...}]
    chunk_index INT
  );
  CREATE INDEX idx_chunks_collection_indexes ON chunks USING GIN (indexes);
  ```

---

### 模式 3：搜索流程的多级融合架构
**文件**：`packages/service/core/dataset/search/defaultRecall/index.ts` L20-150

**流程图**：
```
Input (text query + image queries)
  ↓
Step 1: Image Caption (VLM 生成文本描述)
  ↓
Step 2: Multi-Query Recall (并行)
  ├─ text embedding recall
  ├─ text full-text recall
  ├─ image caption embedding recall
  ├─ image caption full-text recall
  └─ image vector recall (如模型支持)
  ↓
Step 3: Semantic Fusion (在同一语义来源内融合)
  ├─ text: concat(embedding, full-text) with weight
  ├─ image_caption: concat(embedding, full-text) with weight
  └─ image_vector: 独立保留
  ↓
Step 4: Rerank (仅对 text results)
  ↓
Step 5: Multi-Source Merge (文本 + 图片权重合并)
  ├─ 纯文本查询：text 权重 100%
  ├─ 纯图片查询：image 权重 100%
  └─ 混合查询：text 70% + image 30%
  ↓
Step 6: Dedup + Filter + Token Limit
  ↓
Output (ranked chunks with scores)
```

**关键参数**：
- `embeddingWeight`：embedding 和全文的融合权重
- `rerankWeight`：rerank 结果权重
- `similarity`：相似度阈值过滤
- `limit`：token 上限（自动裁剪）

**Chameleon 参考**：
- 表：`retrieval_evaluation` 已支持评估，扩展记录 `fusion_strategy`
- API 参数：`POST /search` 支持 `hybrid_mode`, `embedding_weight`, `similarity_threshold`
- 响应追溯：返回每个 chunk 的得分明细 `{embedding_score, full_text_score, rerank_score, final_score}`

---

## 4. 两个反模式（需要避免）

### 反模式 1：过度复杂的 Chunk Settings 继承链
**问题**：FastGPT 的分块配置在三个层级存在：
- `Dataset.chunkSettings`（全局）
- `DatasetCollection.chunkSettings`（文件级覆盖）
- 运行时 `computedCollectionChunkSettings()` 合并

**危害**：
- 代码行数：merge 逻辑分散在 `controller.ts`、`utils.ts` 多个文件
- 调试困难：用户不清楚最终使用的参数值
- 版本管理：历史 chunks 没有记录使用的分块参数版本号

**Chameleon 建议**：
- 分块策略作为一级资源（`chunking_strategy` 表），版本化管理
- chunks 表添加 `strategy_version_id`，记录生成时使用的策略版本
- Collection 只存储 strategy_id 引用，避免配置冗余

---

### 反模式 2：Vector DB 和 Full-Text 的数据一致性问题
**问题**：FastGPT 同时维护 PostgreSQL pgvector 和 tsvector 两套索引
- 删除 chunk 时需要同时清理两个索引
- embedding 更新不能自动同步 full-text
- 没有显式的数据一致性检查机制

**表现**：
- `deleteDatasetDataVector()` 和 `MongoDatasetData.deleteOne()` 需手动协调
- 如果 vector DB 删除失败，chunk 仍在 MongoDB 中（孤立数据）

**Chameleon 建议**：
- 引入"索引版本号" concept：chunks 表添加 `vector_version`, `fulltext_version`
- 实现 `POST /knowledge/{kb_id}/verify-consistency` 接口，检测孤立 chunk
- 添加数据修复 job：自动补充缺失的 embedding 或 tsvector

---

## 5. 给 Chameleon 的三条最高优先级 RAG 升级建议

### 建议 1：Token-Based Chunking 系统（3-4 周）
**当前状态**：仅支持字符级切分（`backend/chameleon-api/src/chameleon/api/knowledge/chunker.py`）

**目标增强**：
```python
# 新增 TokenChunker 类
class TokenChunker:
    def __init__(self, model_name: str, chunk_token_size: int = 512, overlap: int = 50):
        self.tokenizer = get_tokenizer(model_name)  # 关联 embedding 模型的 tokenizer
        self.chunk_token_size = chunk_token_size
        self.overlap = overlap
    
    def split(self, text: str) -> List[Chunk]:
        # 返回 tokens 计数准确的 chunks
        pass
```

**数据库改造**：
```sql
ALTER TABLE chunks ADD COLUMN strategy_config JSONB;
-- 记录 {chunker_type: 'token', model: 'text-embedding-3-large', token_size: 512, overlap: 50}

ALTER TABLE documents ADD COLUMN chunking_strategy_id UUID REFERENCES chunking_strategies(id);
-- 版本化管理分块策略
```

**API 改造**：
```
POST /knowledge/{kb_id}/set-chunking-strategy
Body: {strategy_type: 'token', model: 'text-embedding-3-large', chunk_size: 512}
```

---

### 建议 2：分块策略可视化编辑器 + hit-test UI（2-3 周）
**当前状态**：前端 `/kbs` 只支持文档管理和简单的搜索测试

**新增模块**：
```
/kbs/{kb_id}/chunking-preview
├─ 左侧：原文预览（带分块边界）
├─ 中间：chunk 列表（可展开查看原文位置）
├─ 右侧：参数调整面板
│   ├─ 选择 chunker 类型 (char/token/paragraph)
│   ├─ 调整参数 (size/overlap/delimiters)
│   └─ 实时预览效果
└─ 底部：Apply & Rechunk 按钮
```

**搜索测试增强**：
```
POST /knowledge/{kb_id}/search-test
Response: {
  query: "用户问题",
  chunks: [
    {
      id: "chunk_1",
      text: "...",
      score: 0.85,
      score_breakdown: {
        embedding: 0.9,
        full_text: 0.8,
        rerank: null
      },
      source_doc: "document.pdf",
      page: 5,
      char_range: [100, 200]  // 原文位置
    }
  ]
}
```

---

### 建议 3：向量/全文一致性检查 + 自修复（2 周）
**当前状态**：没有数据一致性保证机制

**实现方案**：
```python
# 新增后端任务
class ConsistencyChecker:
    async def verify_kb(self, kb_id: str):
        """检测向量/全文不一致的 chunks"""
        # 1. 查找 MongoDB chunks 中存在但 pgvector 中不存在的记录
        # 2. 查找 tsvector 分词异常的 chunks
        # 3. 生成一致性报告
        
        report = {
            orphaned_vectors: [...],  # MongoDB 中有但向量库没有
            orphaned_fulltext: [...],  # MongoDB 中有但全文索引没有
            mismatched_versions: [...]  # 版本号不一致
        }
        return report
    
    async def repair_kb(self, kb_id: str, chunk_ids: List[str]):
        """修复指定 chunks 的向量/全文索引"""
        # 1. 重新生成 embedding
        # 2. 重新生成 tsvector
        # 3. 更新 MongoDB 版本号
```

**前端展示**：
```
/kbs/{kb_id}/consistency-check
├─ 检查进度条
├─ 问题列表
│   ├─ "5 个 chunks 缺失向量索引"
│   ├─ "3 个 chunks 全文索引过期"
│   └─ "自动修复" 按钮
└─ 修复历史日志
```

**数据库**：
```sql
CREATE TABLE consistency_checks (
  id UUID PRIMARY KEY,
  kb_id UUID,
  created_at TIMESTAMP,
  status ENUM('running', 'completed', 'failed'),
  issues JSONB,  -- {orphaned_vectors: [], orphaned_fulltext: [], ...}
  repair_count INT
);
```

---

## 总结

FastGPT 的 RAG 架构优势在于：
1. **多策略分块**：token/paragraph/char 灵活组合
2. **分层组织**：Dataset → Collection → Data 清晰的继承链
3. **完整追溯**：每次搜索记录所有中间步骤的 LLM 消耗和打分明细
4. **富媒体支持**：优先级设计，文本 > 图片描述 > 图片向量

Chameleon 的短期升级方向应该是：优先实现 **token-based chunking** 和 **搜索测试 UI**，这两项收益最高且实现难度最低。中期可引入版本化策略管理和数据一致性检查，为后续的 "问答对生成" 和 "图片解析" 奠定基础。

