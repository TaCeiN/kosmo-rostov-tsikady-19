import { describe, it, expect, vi } from 'vitest';
import { pollJob, JobPollEvent } from '../src/features/job/polling';
import { AnalyzeJobStatusResponse } from '../src/types/domain';
import { ApiError } from '../src/api/client';

describe('Job Polling State Machine', () => {
  it('handles queued -> running -> done lifecycle', async () => {
    const events: JobPollEvent[] = [];
    const mockResponses: AnalyzeJobStatusResponse[] = [
      { status: 'queued', stage: 'в очереди', progress: 0.0 },
      { status: 'running', stage: 'тянем спутники и погоду', progress: 0.1 },
      {
        status: 'done',
        stage: 'готово',
        progress: 1.0,
        result: {
          series: [],
          anomalies: [],
          summary: { rows: 10, reconstructed: 5, observed: 5, anomaly_periods: 0, worst_z: null },
        },
      },
    ];

    let callCount = 0;
    const fetchStatus = vi.fn().mockImplementation(async () => {
      const resp = mockResponses[callCount];
      callCount++;
      return resp;
    });

    await pollJob({
      jobId: 'test-123',
      fetchStatus,
      intervalMs: 1, // fast for test
      onEvent: (ev) => events.push(ev),
    });

    expect(fetchStatus).toHaveBeenCalledTimes(3);
    expect(events.some((e) => e.type === 'status' && e.data.status === 'queued')).toBe(true);
    expect(events.some((e) => e.type === 'status' && e.data.status === 'running')).toBe(true);
    const lastEvent = events[events.length - 1];
    expect(lastEvent?.type).toBe('done');
  });

  it('handles 404 job lost error', async () => {
    const events: JobPollEvent[] = [];
    const fetchStatus = vi.fn().mockRejectedValue(new ApiError(404, 'Not Found'));

    await pollJob({
      jobId: 'lost-123',
      fetchStatus,
      intervalMs: 1,
      onEvent: (ev) => events.push(ev),
    });

    expect(events.length).toBe(1);
    expect(events[0]?.type).toBe('lost');
    if (events[0]?.type === 'lost') {
      expect(events[0].message).toContain('Задача не найдена');
    }
  });

  it('handles status: error from backend', async () => {
    const events: JobPollEvent[] = [];
    const fetchStatus = vi.fn().mockResolvedValue({
      status: 'error',
      progress: 1.0,
      error: 'за выбранной областью нет ни одного наблюдения',
    });

    await pollJob({
      jobId: 'err-123',
      fetchStatus,
      intervalMs: 1,
      onEvent: (ev) => events.push(ev),
    });

    expect(events.some((e) => e.type === 'error')).toBe(true);
    const errEvent = events.find((e) => e.type === 'error');
    if (errEvent && errEvent.type === 'error') {
      expect(errEvent.message).toContain('нет ни одного наблюдения');
    }
  });
});
