/** P8.1 占位；P8.5 落地真实数据卡片 + recharts 时序图 */

export const DashboardPage = () => (
  <div className="p-8">
    <h1 className="font-serif text-3xl text-stone-900">Dashboard</h1>
    <p className="mt-4 text-sm text-stone-500">控制台主页（占位）</p>
    <div className="mt-8 grid grid-cols-4 gap-4">
      {[
        { label: '今日调用', value: '—' },
        { label: '成功率', value: '—' },
        { label: 'Token 消耗', value: '—' },
        { label: '活跃应用', value: '—' },
      ].map(item => (
        <div
          key={item.label}
          className="rounded-lg bg-[var(--color-paper)] p-6 shadow-card"
        >
          <div className="text-xs text-stone-500">{item.label}</div>
          <div className="mt-2 font-mono text-2xl text-stone-900">{item.value}</div>
        </div>
      ))}
    </div>
  </div>
);
