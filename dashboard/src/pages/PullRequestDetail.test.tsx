import { StrictMode } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PullRequestDetail } from './PullRequestDetail';
import { workspaceFixtures } from '../demo/fixtures';

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ workspaceVersion: 0, activeWorkspace: { id: 1 } }) }));

describe('pull request request lifecycle', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('shows successful detail when StrictMode cancels its superseded initial request', async () => {
    const sample = workspaceFixtures(1);
    const detail = sample.prDetail(sample.prs[0]);
    vi.stubGlobal('fetch', (_input: RequestInfo | URL, options?: RequestInit) => new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response(JSON.stringify(detail))), 10);
      const abort = () => { clearTimeout(timer); reject(new DOMException('signal is aborted without reason', 'AbortError')); };
      if (options?.signal?.aborted) abort();
      else options?.signal?.addEventListener('abort', abort, { once: true });
    }));

    render(<StrictMode><MemoryRouter initialEntries={['/pull-requests/101']}><Routes><Route path="/pull-requests/:pullRequestId" element={<PullRequestDetail />} /></Routes></MemoryRouter></StrictMode>);

    expect(await screen.findByRole('heading', { name: '#241 — Harden payment webhook signature validation' })).toBeInTheDocument();
    expect(screen.queryByText('Unable to load pull request')).not.toBeInTheDocument();
  });
});
