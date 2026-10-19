import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
vi.hoisted(() => vi.stubEnv('VITE_CODEGATE_DEMO', 'true'));
import App from '../App';
import { installDemoTransport } from './transport';

describe('interactive demo experience', () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  async function open(path: string) {
    window.history.replaceState({}, '', path);
    vi.stubGlobal('fetch', async () => { throw new Error('Unexpected real network request'); });
    installDemoTransport(true);
    return render(<App />);
  }

  it('filters and paginates sample PRs, opens detail and persists an understood lesson', async () => {
    const user = userEvent.setup();
    const view = await open('/pull-requests');
    await screen.findByText('Interactive demo');
    expect(screen.getByText('Sample data · Changes stay in this browser')).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Policy filter'), 'BLOCK');
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.queryByText('Cache product search results')).not.toBeInTheDocument();
    await user.type(screen.getByRole('searchbox'), 'webhook');
    await user.click(screen.getByRole('link', { name: 'Harden payment webhook signature validation' }));
    expect(await screen.findByRole('button', { name: 'Retry Analysis' })).toBeDisabled();
    await user.click((await screen.findAllByRole('button', { name: 'Mark as Understood' }))[0]);
    expect(screen.getByRole('button', { name: 'Learned & Understood' })).toBeInTheDocument();
    view.unmount();
    await open('/pull-requests/101');
    expect(await screen.findByRole('button', { name: 'Learned & Understood' })).toBeInTheDocument();
  });

  it('switches the actual workspace data and explains unavailable external operations', async () => {
    const user = userEvent.setup();
    await open('/repositories');
    await screen.findByRole('link', { name: 'acme/payments-api' });
    await user.click(screen.getByRole('button', { name: /Acme Engineering/ }));
    await user.click(screen.getByRole('button', { name: 'Orbit Labs' }));
    expect(await screen.findByRole('link', { name: 'orbit/mobile-app' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'acme/payments-api' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Integrations' }));
    await user.click(screen.getByRole('link', { name: /GitHub App/ }));
    expect(await screen.findByRole('button', { name: 'Connect GitHub' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeDisabled();
    expect(screen.getByText(/A live backend is required/)).toBeInTheDocument();
  });

  it('saves repository settings only in this browser and offers a useful help dialog', async () => {
    const user = userEvent.setup();
    await open('/repositories/1');
    const command = await screen.findByLabelText('Test Command');
    await user.clear(command);
    await user.type(command, 'pytest -q');
    await user.click(screen.getByRole('button', { name: 'Save Configuration' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Sample configuration saved in this browser');
    await user.click(screen.getByRole('button', { name: 'Demo help' }));
    expect(screen.getByRole('dialog', { name: 'Explore the CodeGate demo' })).toHaveTextContent('GitHub OAuth');
    await user.click(screen.getByRole('button', { name: 'Close help' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
