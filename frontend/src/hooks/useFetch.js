import { useCallback, useEffect, useState } from "react";

/** Runs `fn(signal)` whenever `deps` change. Keeps the previous data on screen while refetching. */
export function useFetch(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fn(ctrl.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (error.name !== "AbortError") setState((s) => ({ ...s, error, loading: false }));
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, refetch };
}
