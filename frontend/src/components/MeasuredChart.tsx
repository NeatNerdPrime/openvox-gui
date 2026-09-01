import { useEffect, useRef, useState, type ReactNode } from 'react';

/**
 * Measure the parent and only paint when width > 0.
 * Recharts ResponsiveContainer often first-measures 0 and stays blank.
 */
export function MeasuredArea({
  height,
  children,
}: {
  height: number;
  children: (width: number) => ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const apply = () => {
      const w = Math.floor(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} style={{ width: '100%', minWidth: 0, height }}>
      {width > 0 ? children(width) : null}
    </div>
  );
}
