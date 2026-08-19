import { useEffect, useRef, useState } from "react";

// data === undefined -> loading, data === null -> 404 (not available yet)
export default function usePolling(fetcher, deps, intervalMs = 4000) {
  const [data, setData] = useState(undefined);
  const [error, setError] = useState(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const result = await fetcherRef.current();
        if (alive) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(err);
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error };
}
