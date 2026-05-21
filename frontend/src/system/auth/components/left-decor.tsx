/** 登录页左侧背景装饰（复刻 waveflow 风格）
 *
 * - 远景灰色点阵（radial mask 中心实边缘羽化）
 * - 4 个 SVG 几何浮件：同心圆 / 圆角方 / 三角 / 圆点，CSS keyframes 缓慢漂浮
 * - 鼠标交互：
 *   a) 480px 柔光跟随鼠标，multiply 混合点亮局部
 *   b) SVG 动态连线：鼠标 → 最近 2 个浮件画线 + 浮件之间互连
 *
 * 浮件本身不跟随鼠标，只缓慢漂浮（避免视差晃动干扰阅读）。
 */

import * as React from 'react';

export const LeftDecor: React.FC = () => {
  const layerRef = React.useRef<HTMLDivElement>(null);
  const glowRef = React.useRef<HTMLDivElement>(null);
  const svgRef = React.useRef<SVGSVGElement>(null);
  const geo1Ref = React.useRef<HTMLDivElement>(null);
  const geo2Ref = React.useRef<HTMLDivElement>(null);
  const geo3Ref = React.useRef<HTMLDivElement>(null);
  const geo4Ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const layer = layerRef.current;
    const parent = layer?.parentElement;
    if (!layer || !parent) return;

    const geos = [geo1Ref.current, geo2Ref.current, geo3Ref.current, geo4Ref.current];
    const mouse = { x: -1000, y: -1000, active: false };

    const onMove = (e: MouseEvent) => {
      const rect = parent.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
      if (glowRef.current) {
        glowRef.current.style.left = mouse.x + 'px';
        glowRef.current.style.top = mouse.y + 'px';
        glowRef.current.style.opacity = '1';
      }
    };

    const onLeave = () => {
      mouse.x = -1000;
      mouse.y = -1000;
      mouse.active = false;
      if (glowRef.current) glowRef.current.style.opacity = '0';
    };

    parent.addEventListener('mousemove', onMove);
    parent.addEventListener('mouseleave', onLeave);

    let rafId = 0;
    const tick = () => {
      rafId = requestAnimationFrame(tick);
      const svg = svgRef.current;
      if (!svg) return;
      const rect = parent.getBoundingClientRect();
      if (!rect.width) return;

      svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);

      const points: { cx: number; cy: number }[] = [];
      for (const g of geos) {
        if (!g) continue;
        const r = g.getBoundingClientRect();
        points.push({
          cx: r.left + r.width / 2 - rect.left,
          cy: r.top + r.height / 2 - rect.top,
        });
      }

      const lines: string[] = [];
      const MAX_DIST = 240;

      if (mouse.active) {
        const sorted = points
          .map(p => ({ ...p, d: Math.hypot(mouse.x - p.cx, mouse.y - p.cy) }))
          .sort((a, b) => a.d - b.d);
        for (let i = 0; i < Math.min(2, sorted.length); i++) {
          const p = sorted[i];
          if (p.d < MAX_DIST) {
            const op = ((1 - p.d / MAX_DIST) * 0.55).toFixed(3);
            lines.push(
              `<line x1="${mouse.x.toFixed(1)}" y1="${mouse.y.toFixed(1)}" x2="${p.cx.toFixed(1)}" y2="${p.cy.toFixed(1)}" stroke="#0ea5e9" stroke-width="0.8" opacity="${op}" />`,
            );
          }
        }
      }

      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const d = Math.hypot(points[i].cx - points[j].cx, points[i].cy - points[j].cy);
          if (d < MAX_DIST) {
            const op = ((1 - d / MAX_DIST) * 0.25).toFixed(3);
            lines.push(
              `<line x1="${points[i].cx.toFixed(1)}" y1="${points[i].cy.toFixed(1)}" x2="${points[j].cx.toFixed(1)}" y2="${points[j].cy.toFixed(1)}" stroke="#0ea5e9" stroke-width="0.5" opacity="${op}" />`,
            );
          }
        }
      }

      svg.innerHTML = lines.join('');
    };
    tick();

    return () => {
      parent.removeEventListener('mousemove', onMove);
      parent.removeEventListener('mouseleave', onLeave);
      cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <div ref={layerRef} className="pointer-events-none absolute inset-0">
      {/* 点阵 */}
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: 'radial-gradient(circle, #d6d3d1 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          opacity: 0.35,
          maskImage: 'radial-gradient(ellipse at 70% 50%, black 30%, transparent 80%)',
          WebkitMaskImage: 'radial-gradient(ellipse at 70% 50%, black 30%, transparent 80%)',
        }}
      />

      {/* 动态连线 SVG 层 */}
      <svg ref={svgRef} className="absolute inset-0 z-[1]" preserveAspectRatio="none" />

      {/* 鼠标柔光 */}
      <div
        ref={glowRef}
        className="absolute z-[2] rounded-full opacity-0 transition-opacity duration-300"
        style={{
          width: '480px',
          height: '480px',
          background: 'radial-gradient(circle, rgba(14,165,233,0.10), transparent 70%)',
          transform: 'translate(-50%, -50%)',
          mixBlendMode: 'multiply',
        }}
      />

      {/* 同心圆（sky） */}
      <div
        ref={geo1Ref}
        className="absolute z-[3]"
        style={{ top: '22%', right: '18%', animation: 'decor-drift-1 7s ease-in-out infinite' }}
      >
        <svg width="48" height="48" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="22" fill="none" stroke="#0ea5e9" strokeWidth="1" opacity="0.5" />
          <circle cx="24" cy="24" r="14" fill="#0ea5e9" opacity="0.18" />
        </svg>
      </div>

      {/* 圆角方（mint） */}
      <div
        ref={geo2Ref}
        className="absolute z-[3]"
        style={{ top: '50%', right: '8%', animation: 'decor-drift-2 8s ease-in-out infinite' }}
      >
        <svg width="36" height="36" viewBox="0 0 36 36">
          <rect x="2" y="2" width="32" height="32" rx="6" fill="none" stroke="#10b981" strokeWidth="1" opacity="0.6" />
          <rect x="8" y="8" width="20" height="20" rx="3" fill="#10b981" opacity="0.15" />
        </svg>
      </div>

      {/* 三角（amber） */}
      <div
        ref={geo3Ref}
        className="absolute z-[3]"
        style={{ top: '70%', right: '28%', animation: 'decor-drift-3 9s ease-in-out infinite' }}
      >
        <svg width="40" height="40" viewBox="0 0 40 40">
          <polygon points="20,4 36,32 4,32" fill="none" stroke="#f59e0b" strokeWidth="1" opacity="0.55" />
          <polygon points="20,12 30,28 10,28" fill="#f59e0b" opacity="0.18" />
        </svg>
      </div>

      {/* 圆点（violet） */}
      <div
        ref={geo4Ref}
        className="absolute z-[3]"
        style={{ top: '38%', right: '35%', animation: 'decor-drift-1 6s ease-in-out infinite' }}
      >
        <svg width="28" height="28" viewBox="0 0 28 28">
          <circle cx="14" cy="14" r="3" fill="#8b5cf6" />
          <circle cx="14" cy="14" r="12" fill="none" stroke="#8b5cf6" strokeWidth="1" opacity="0.4" />
        </svg>
      </div>
    </div>
  );
};
