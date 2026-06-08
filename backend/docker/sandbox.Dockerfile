# Chameleon agentkit 沙箱执行镜像（T4-2 Phase 3 真隔离）—— 已验证可构建 + 容器隔离 e2e 通过。
#
# 构建（context = backend/）：
#   docker build -f docker/sandbox.Dockerfile -t chm-agent-sandbox:latest .
# 启用：CHAMELEON_SANDBOX_RUNTIME=docker + CHAMELEON_SANDBOX_IMAGE=chm-agent-sandbox:latest
#   → @agent(sandboxed=True) 的 handle 在 --network none --read-only 容器内跑，ctx 资源经
#     主进程 broker（凭据/DB 全留主进程），agent 源码运行时只读挂载（见 build_docker_command）。
#
# 精简前提：agentkit 已去 providers-base→data 重依赖（运行时协议类型在 core.runtime_types），
# child 只需 core(轻) + agentkit + mcp，不拉 sqlalchemy/asyncpg/jieba/docker → 镜像 ~278MB。
FROM python:3.12-slim
WORKDIR /sbx
COPY chameleon-core /sbx/core
COPY chameleon-agentkit /sbx/agentkit
RUN pip install --no-cache-dir /sbx/core \
 && pip install --no-cache-dir /sbx/agentkit \
 && rm -rf /sbx
# agent 源码运行时经 -v <src>:/agent_src:ro 挂入 + PYTHONPATH=/agent_src
ENTRYPOINT ["python", "-m", "chameleon.agentkit._sandbox_child"]
