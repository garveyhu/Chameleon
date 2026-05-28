/** 会话管理端点（/v1/sessions/*）
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/sessions/api.py + schemas.py
 * 鉴权：current_app_or_admin（api_key 或 admin JWT）
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'sessions.list',
    group: 'sessions',
    order: 10,
    title: '会话列表',
    method: 'GET',
    path: '/v1/sessions',
    auth: 'bearer-key',
    desc: '分页列当前 key 范围内的历史会话。app 作用域 key 会自动锁定为绑定的 agent；user 参数按终端用户外部 id 过滤。',
    queryParams: [
      { name: 'page', type: 'integer', required: false, default: 1, desc: '页码，从 1 开始' },
      {
        name: 'page_size',
        type: 'integer',
        required: false,
        default: 10,
        desc: '每页条数，1 ≤ page_size ≤ 100',
      },
      {
        name: 'agent_key',
        type: 'string',
        required: false,
        desc: 'agent 过滤 —— app 作用域 key 会忽略此参数（自动锁定为 scope_ref）',
      },
      {
        name: 'user',
        type: 'string',
        required: false,
        desc: '按终端用户外部 id 过滤（对应 sessions.end_user_id）',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            items: [
              {
                id: 1,
                session_id: 'sess_01H...',
                agent_key: 'agt_my_app',
                app_id: 'app_xxx',
                end_user_id: 'end-user-id-12345',
                title: '产品咨询',
                last_message_at: '2026-05-28T03:21:00Z',
                created_at: '2026-05-28T03:20:00Z',
                updated_at: '2026-05-28T03:21:00Z',
              },
            ],
            total: 42,
            page: 1,
            page_size: 10,
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/sessions?user=end-user-id-12345&page=1&page_size=10' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'sessions.get',
    group: 'sessions',
    order: 20,
    title: '会话详情',
    method: 'GET',
    path: '/v1/sessions/{session_id}',
    auth: 'bearer-key',
    desc: '取单个会话的元信息。',
    pathParams: [{ name: 'session_id', type: 'string', required: true, desc: '会话 ID（雪花字符串）' }],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            id: 1,
            session_id: 'sess_01H...',
            agent_key: 'agt_my_app',
            app_id: 'app_xxx',
            end_user_id: 'end-user-id-12345',
            title: '产品咨询',
            last_message_at: '2026-05-28T03:21:00Z',
            created_at: '2026-05-28T03:20:00Z',
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/sessions/sess_01H...' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'sessions.messages',
    group: 'sessions',
    order: 30,
    title: '会话消息列表',
    method: 'GET',
    path: '/v1/sessions/{session_id}/messages',
    auth: 'bearer-key',
    desc: '按 seq 正序加载某历史会话的消息列表（含分支 fork 出的 sibling 消息）。',
    pathParams: [{ name: 'session_id', type: 'string', required: true, desc: '会话 ID' }],
    queryParams: [
      { name: 'page', type: 'integer', required: false, default: 1, desc: '页码' },
      { name: 'page_size', type: 'integer', required: false, default: 20, desc: '每页条数，最大 200' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            items: [
              {
                id: 1,
                session_id: 'sess_01H...',
                seq: 1,
                role: 'user',
                content: '你好',
                created_at: '2026-05-28T03:20:00Z',
              },
              {
                id: 2,
                session_id: 'sess_01H...',
                seq: 2,
                role: 'assistant',
                content: '你好！需要我帮你做什么？',
                usage: { total_tokens: 40 },
                parent_message_id: null,
                created_at: '2026-05-28T03:20:01Z',
              },
            ],
            total: 2,
            page: 1,
            page_size: 20,
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/sessions/sess_01H.../messages' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'sessions.delete',
    group: 'sessions',
    order: 40,
    title: '删除会话',
    method: 'POST',
    path: '/v1/sessions/{session_id}/delete',
    auth: 'bearer-key',
    desc: '软删一个会话（status 置为 deleted），不物理清除消息。',
    pathParams: [{ name: 'session_id', type: 'string', required: true, desc: '会话 ID' }],
    responses: [
      {
        code: 200,
        desc: '返回被删除的会话 item（含最新状态）',
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/sessions/sess_01H.../delete' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'sessions.regenerate',
    group: 'sessions',
    order: 50,
    title: '重新生成',
    method: 'POST',
    path: '/v1/sessions/{session_id}/messages/{message_id}/regenerate',
    auth: 'bearer-key',
    desc: '对某条 assistant 消息重新生成 → 新 assistant child 挂同 user 父，形成兄弟分支。老 assistant 不删。',
    pathParams: [
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
      { name: 'message_id', type: 'integer', required: true, desc: '要重新生成的 assistant 消息 id' },
    ],
    responses: [
      {
        code: 200,
        desc: '返回新生成的 assistant message item',
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/sessions/sess_01H.../messages/123/regenerate' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'sessions.edit-and-resend',
    group: 'sessions',
    order: 60,
    title: '编辑并重发',
    method: 'POST',
    path: '/v1/sessions/{session_id}/messages/{message_id}/edit-and-resend',
    auth: 'bearer-key',
    desc: '编辑某 user message → 新 user sibling 分支 + 自动 invoke 新 assistant。老消息不删。',
    pathParams: [
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
      { name: 'message_id', type: 'integer', required: true, desc: '要编辑的 user 消息 id' },
    ],
    bodyParams: [
      {
        name: 'new_content',
        type: 'string',
        required: true,
        desc: '新的用户输入内容（1 ≤ len ≤ 20000）',
        example: '帮我查一下退款流程',
      },
    ],
    responses: [
      {
        code: 200,
        desc: '返回新生成的 user message item（其后由系统自动产生新 assistant child）',
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/sessions/sess_01H.../messages/123/edit-and-resend' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "new_content": "帮我查一下退款流程" }'`,
  },
];

export default ENDPOINTS;
