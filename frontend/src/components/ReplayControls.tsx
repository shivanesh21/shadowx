import React from 'react';
import {
  Play,
  Pause,
  SkipForward,
  RotateCcw,
  Zap,
} from 'lucide-react';
import { FactoryEvent } from '../types';

interface ReplayControlsProps {
  events: FactoryEvent[];
  currentIndex: number;
  isPlaying: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onStepForward: () => void;
  onSeek: (index: number) => void;
  onSpeedChange: (speed: number) => void;
  onReset: () => void;
  onExitReplay: () => void;
}

export const ReplayControls: React.FC<ReplayControlsProps> = ({
  events,
  currentIndex,
  isPlaying,
  speed,
  onPlay,
  onPause,
  onStepForward,
  onSeek,
  onSpeedChange,
  onReset,
  onExitReplay,
}) => {
  const total = events.length;
  const currentEvent = total > 0 && currentIndex > 0 ? events[currentIndex - 1] : null;

  return (
    <div className="bg-gray-900/90 border border-indigo-900/60 rounded-xl p-3 shadow-2xl backdrop-blur-md mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Replay Status & Event Info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-950/80 border border-indigo-700/60 text-indigo-300 text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
            REPLAY MODE
          </div>
          <div className="text-xs font-mono text-gray-300">
            Event <span className="text-indigo-400 font-bold">{currentIndex}</span> of{' '}
            <span className="text-gray-400">{total}</span>
          </div>
          {currentEvent && (
            <div className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-800 text-[11px] font-mono text-gray-300 border border-gray-700">
              <span className="text-indigo-400 font-semibold">{currentEvent.event_type}</span>
              {(currentEvent as any).stage && (
                <span className="text-gray-400">({(currentEvent as any).stage})</span>
              )}
            </div>
          )}
        </div>

        {/* Center: Controls (Play/Pause/Step/Reset) */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={onReset}
            title="Reset to beginning"
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white transition-colors border border-gray-700"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {isPlaying ? (
            <button
              onClick={onPause}
              title="Pause"
              className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <Pause className="w-3.5 h-3.5" />
              <span>Pause</span>
            </button>
          ) : (
            <button
              onClick={onPlay}
              disabled={currentIndex >= total}
              title="Play"
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Play</span>
            </button>
          )}

          <button
            onClick={onStepForward}
            disabled={currentIndex >= total || isPlaying}
            title="Step 1 event forward"
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 hover:text-white transition-colors border border-gray-700"
          >
            <SkipForward className="w-3.5 h-3.5" />
          </button>

          {/* Speed Presets */}
          <div className="ml-2 flex items-center gap-1 bg-gray-950 p-0.5 rounded-lg border border-gray-800 text-[11px] font-mono">
            {[0.5, 1, 2, 5, 10].map((s) => (
              <button
                key={s}
                onClick={() => onSpeedChange(s)}
                className={`px-1.5 py-0.5 rounded transition-colors ${
                  speed === s
                    ? 'bg-indigo-600 text-white font-bold'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {s}x
              </button>
            ))}
            <button
              onClick={() => onSpeedChange(999)}
              title="Instant Replay"
              className={`px-1.5 py-0.5 rounded transition-colors flex items-center gap-0.5 ${
                speed === 999
                  ? 'bg-cyan-600 text-white font-bold'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <Zap className="w-3 h-3" />
              <span>Max</span>
            </button>
          </div>
        </div>

        {/* Right: Exit Replay */}
        <div>
          <button
            onClick={onExitReplay}
            className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 transition-colors"
          >
            Exit Replay
          </button>
        </div>
      </div>

      {/* Scrubber slider */}
      <div className="mt-2.5 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={total}
          value={currentIndex}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
        />
        <span className="text-[10px] font-mono text-gray-400 whitespace-nowrap">
          {total > 0 ? `${Math.round((currentIndex / total) * 100)}%` : '0%'}
        </span>
      </div>
    </div>
  );
};
