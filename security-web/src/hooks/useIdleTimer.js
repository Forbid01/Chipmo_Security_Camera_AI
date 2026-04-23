import { useEffect, useRef, useState } from 'react';

// DOM events that reset the idle timer. Matches the set used by
// most idle-detection libraries — keeps the user "active" through
// the natural rhythm of signup form filling.
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll'];

/**
 * `useIdleTimer(ms, onIdle)` — calls `onIdle()` once after `ms`
 * milliseconds without a user activity event. Returns `[isIdle, reset]`
 * so the caller can render a "still there?" banner or manually
 * restart the timer.
 */
export function useIdleTimer(idleMs, onIdle) {
  const [isIdle, setIsIdle] = useState(false);
  const timerRef = useRef(null);
  const firedRef = useRef(false);

  useEffect(() => {
    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      firedRef.current = false;
      setIsIdle(false);
      timerRef.current = setTimeout(() => {
        setIsIdle(true);
        if (!firedRef.current) {
          firedRef.current = true;
          try {
            onIdle?.();
          } catch {
            // Idle callbacks must never throw — they run from setTimeout
            // and an unhandled exception would crash the React tree.
          }
        }
      }, idleMs);
    };

    ACTIVITY_EVENTS.forEach((ev) =>
      window.addEventListener(ev, reset, { passive: true }),
    );
    reset();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, reset));
    };
  }, [idleMs, onIdle]);

  return [isIdle, () => {
    firedRef.current = false;
    setIsIdle(false);
  }];
}
