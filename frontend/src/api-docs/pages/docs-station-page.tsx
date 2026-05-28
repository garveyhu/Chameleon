/** API 文档站主页（独立全屏 / 不走 MainLayout）
 *
 * 三栏：左侧分组导航 · 中间端点详情 · 右侧 cURL + 响应示例
 * URL 携带 ?endpoint=<id> 支持深链；⌘K / Ctrl+K 聚焦搜索框。
 */
import * as React from 'react';
import { useSearchParams } from 'react-router-dom';

import { ALL_ENDPOINTS, findEndpoint, groupEndpoints } from '@/api-docs/registry/_collect';
import { RequireAuth } from '@/core/components/common/permission-guard';

import { EndpointDetail } from '../components/station/endpoint-detail';
import { ExamplePane } from '../components/station/example-pane';
import { Sidebar } from '../components/station/sidebar';
import { StationHeader } from '../components/station/station-header';

const FIRST_ENDPOINT_ID = ALL_ENDPOINTS[0]?.id ?? '';

export const DocsStationPage = () => {
  const [params, setParams] = useSearchParams();
  const requested = params.get('endpoint');
  const activeId = (requested && findEndpoint(requested)?.id) || FIRST_ENDPOINT_ID;

  // URL 未带 endpoint 时回填一次，让深链稳定
  React.useEffect(() => {
    if (!requested && activeId) {
      setParams({ endpoint: activeId }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = React.useMemo(() => groupEndpoints(ALL_ENDPOINTS), []);
  const endpoint = findEndpoint(activeId);

  const searchRef = React.useRef<HTMLInputElement | null>(null);

  // ⌘K / Ctrl+K 全局聚焦搜索
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // 切换端点 → 主区滚回顶部
  const mainRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [activeId]);

  // {BASE} 在 cURL 模板里用作 origin（不含 /v1）；顶栏右上「通用端点」展示 origin/v1
  const origin = window.location.origin;
  const v1Endpoint = `${origin}/v1`;

  const handleSelect = (id: string) => {
    setParams({ endpoint: id }, { replace: false });
  };

  return (
    <RequireAuth>
    <div className="flex h-screen flex-col bg-[var(--color-warm)]">
      <StationHeader baseUrl={v1Endpoint} />
      <div className="flex min-h-0 flex-1">
        <Sidebar
          groups={groups}
          activeId={activeId}
          onSelect={handleSelect}
          searchInputRef={searchRef}
        />
        <main ref={mainRef} className="min-w-0 flex-1 overflow-y-auto">
          {endpoint ? (
            <EndpointDetail endpoint={endpoint} />
          ) : (
            <div className="flex h-full items-center justify-center text-stone-400">
              该端点不存在
            </div>
          )}
        </main>
        {endpoint && <ExamplePane endpoint={endpoint} baseUrl={origin} />}
      </div>
    </div>
    </RequireAuth>
  );
};
