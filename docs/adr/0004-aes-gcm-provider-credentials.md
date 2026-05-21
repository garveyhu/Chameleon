# ADR 0004：Provider 凭证 AES-256-GCM 加密入库

- **Status**: Accepted
- **Date**: 2026-04

## 背景

Chameleon 接入多个 LLM provider（Dify、FastGPT、OpenAI 兼容厂商），需要存它们的 api_key 到 DB。明文存储会被 DB 泄漏 + dump 直接打穿。

## 决策

`providers.api_key_encrypted` 字段存 AES-256-GCM 密文，密钥从 env `CHAMELEON_CRYPTO_KEY`（32 bytes base64）派生。

## 理由

- **GCM 自带 AEAD**：除了加密还提供数据完整性，篡改即解密失败
- **256-bit**：现代 GPU 也暴力破不动
- **env 中心化密钥**：不入 git；K8s Secret / Vault 集成无缝
- **fail-fast**：production 启动期检查 env 必须设；dev 用 sha256 派生 demo key 但 warn 一次

## 数据格式

`base64(nonce || ciphertext || tag)` —— 12 字节 nonce 每次随机生成，写入密文头。

## 后果

- 失去 master key = 失去所有 provider api_key（业务方需重新配置）
- 主密钥轮换需要 re-encrypt 全部记录（v0.1 未做，靠 admin UI 改 api_key 触发重加密）
- 测试代码也用同一套加密路径（不 bypass），防止生产路径出 bug 测试看不到

## 关联

- ADR-0006 DB-driven 配置
