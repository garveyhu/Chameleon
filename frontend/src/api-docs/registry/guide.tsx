/** 概览类指南页（非端点）—— 能力总览 + 计费说明，帮开发者快速理解复杂能力体系。 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="border-b border-stone-200 px-3 py-2 text-left text-[12px] font-medium text-stone-600">
    {children}
  </th>
);
const Td = ({ children }: { children: React.ReactNode }) => (
  <td className="border-b border-stone-100 px-3 py-2 align-top text-[12.5px] text-stone-700">
    {children}
  </td>
);
const H = ({ children }: { children: React.ReactNode }) => (
  <h2 className="mt-6 mb-2 text-[15px] font-semibold text-stone-900">{children}</h2>
);
const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
    {children}
  </code>
);

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'guide-overview',
    group: 'guide',
    order: 10,
    guide: true,
    title: '能力总览',
    desc: '本平台把「应用」做成伞形概念，统一一套调用协议覆盖对话、检索、图理解、生图、生视频等多模态能力。下面是应用类型 × 能力矩阵。',
    body: (
      <>
        <H>统一调用入口</H>
        <p>
          所有应用都经 <Code>POST /v1/invoke</Code>（原生扁平协议）或{' '}
          <Code>POST /v1/chat/completions</Code>（OpenAI 兼容）调用。<Code>model</Code> /{' '}
          <Code>agent_key</Code> 即应用标识；app 作用域 Key 自动锁定到绑定应用。
        </p>

        <H>应用类型 × 能力矩阵</H>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <Th>应用类型（source）</Th>
                <Th>典型用途</Th>
                <Th>输入</Th>
                <Th>输出</Th>
                <Th>计费</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td>代码应用 / 编排应用 / 外部（对话）</Td>
                <Td>对话问答、RAG、工作流</Td>
                <Td>文本；视觉模型经 /v1/invoke attachments 传图</Td>
                <Td>文本（流式 delta）</Td>
                <Td>按 token</Td>
              </tr>
              <tr>
                <Td>生成应用 · 文生图（绑 image 模型）</Td>
                <Td>文生图</Td>
                <Td>
                  提示词 + <Code>options.gen_params</Code>（尺寸/风格/数量…）
                </Td>
                <Td>
                  Markdown 图片 <Code>![](url)</Code>
                </Td>
                <Td>按张</Td>
              </tr>
              <tr>
                <Td>生成应用 · 图生视频（绑 video 模型）</Td>
                <Td>图生视频</Td>
                <Td>
                  提示词 + <Code>gen_params</Code>（分辨率/时长）+{' '}
                  <Code>options.input_images</Code>（首帧）
                </Td>
                <Td>
                  Markdown 视频链接 <Code>[▶视频](url)</Code>
                </Td>
                <Td>按秒（分辨率分档）</Td>
              </tr>
            </tbody>
          </table>
        </div>

        <H>多模态输入</H>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <b>图理解（VLM）</b>：经 <Code>/v1/invoke</Code> 的{' '}
            <Code>attachments</Code> 传图片（OpenAI 兼容端点的 content 仅支持纯字符串，
            不支持内容块数组）。仅应用绑定视觉模型（如 qwen-vl）时生效。
          </li>
          <li>
            <b>生成参数发现</b>：不同生成模型可调参数不同，UI 经声明式 param-spec 渲染；
            程序化集成时传你需要的 <Code>gen_params</Code> 子集即可，未知字段忽略。
          </li>
        </ul>

        <H>会话与身份</H>
        <p>
          传 <Code>session_id</Code> 续接多轮；<Code>user</Code> 标识终端用户（会话归属 /
          按用户统计 / 计费维度）。媒体产物 URL 为对象存储签名地址，读取时自动重签，不会失效。
        </p>
      </>
    ),
  },
  {
    id: 'guide-billing',
    group: 'guide',
    order: 20,
    guide: true,
    title: '计费说明',
    desc: '平台按调用真实消耗计费，币种为人民币（元）。价目在「设置 → 模型 → 计费/价目」维护，按时间版本存档（改价不影响历史账单）。',
    body: (
      <>
        <H>计费单位</H>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <Th>能力</Th>
                <Th>计费单位</Th>
                <Th>说明</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td>对话 / 文本（LLM）</Td>
                <Td>按 token（元 / 1K）</Td>
                <Td>输入、输出分别计价</Td>
              </tr>
              <tr>
                <Td>向量（embedding）</Td>
                <Td>按 token（元 / 1K）</Td>
                <Td>仅输入计费</Td>
              </tr>
              <tr>
                <Td>文生图</Td>
                <Td>按张（元 / 张）</Td>
                <Td>数量 = gen_params.n</Td>
              </tr>
              <tr>
                <Td>图生视频</Td>
                <Td>按秒（元 / 秒）</Td>
                <Td>分辨率分档（如 720P / 1080P 不同价），时长 = gen_params.duration</Td>
              </tr>
            </tbody>
          </table>
        </div>

        <H>成本可观测</H>
        <p>
          每次调用的成本落入调用账本（trace），可在「观测 → 仪表盘 → 成本」按应用 / 模型 /
          终端用户 / 渠道维度下钻。成本按调用当时生效的价目计算并存档，可重放、不被后续改价影响。
        </p>

        <H>本地模型</H>
        <p>
          本地部署的模型（如本地 ComfyUI 生图）默认无价目（成本计 0 / 不计费）；如需核算可在价目页为其设价。
        </p>
      </>
    ),
  },
];

export default ENDPOINTS;
