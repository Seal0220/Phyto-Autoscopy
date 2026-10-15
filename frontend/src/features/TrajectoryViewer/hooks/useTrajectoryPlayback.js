"use client";

import { useEffect, useMemo, useState } from "react";
import { trajectoryFrames, trajectoryThroughFrame } from "../lib/trajectoryPlaybackUtils";
import { TRAJECTORY_PLAYBACK_INTERVAL_MS } from "../trajectoryViewerConfig";

export default function useTrajectoryPlayback({
  analysisId,
  trajectory,
  waiting,
}) {
  const frames = useMemo(() => trajectoryFrames(trajectory), [trajectory]);
  const [cursorKey, setCursorKey] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [pageVisible, setPageVisible] = useState(true);
  const cursor = cursorKey === null ? null : Math.max(0, frames.findIndex((frame) => frame.key === cursorKey));
  const frame = cursor === null ? null : frames[cursor] || null;
  const shownTrajectory = useMemo(
    () => trajectoryThroughFrame(trajectory, frames, cursor),
    [trajectory, frames, cursor],
  );

  useEffect(() => {
    setCursorKey(null);
    setPlaying(false);
  }, [analysisId]);

  useEffect(() => {
    const change = () => setPageVisible(!document.hidden);
    change();
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);

  useEffect(() => {
    if (!playing || waiting || !pageVisible || !frame) return undefined;
    const timer = setTimeout(() => {
      if (cursor + 1 < frames.length) setCursorKey(frames[cursor + 1].key);
      else setPlaying(false);
    }, TRAJECTORY_PLAYBACK_INTERVAL_MS / speed);
    return () => clearTimeout(timer);
  }, [playing, waiting, pageVisible, frame, cursor, frames, speed]);

  const restart = () => {
    if (!frames.length) return;
    setCursorKey(frames[0].key);
    setPlaying(true);
  };
  const togglePlayback = () => {
    if (playing) setPlaying(false);
    else if (cursor === null || cursor >= frames.length - 1) restart();
    else setPlaying(true);
  };
  const showAll = () => {
    setPlaying(false);
    setCursorKey(null);
  };

  return { frames, cursor, frame, shownTrajectory, playing, speed, setSpeed, restart, togglePlayback, showAll };
}
