import asyncio
from types import SimpleNamespace

from pr_agent.algo.ai_handlers import litellm_helpers


def test_cleanup_wait_rechecks_early_timer_wakeup(monkeypatch):
    async def run():
        clock = [10.0]
        pending = {object()}
        timeouts = []

        async def early_wait(tasks, timeout):
            assert tasks == pending
            timeouts.append(timeout)
            clock[0] += min(0.04, timeout)
            return set(), pending

        monkeypatch.setattr(litellm_helpers.asyncio, 'get_running_loop',
                            lambda: SimpleNamespace(time=lambda: clock[0]))
        monkeypatch.setattr(litellm_helpers.asyncio, 'wait', early_wait)
        await litellm_helpers._wait_for_tasks_until(pending, 0.1)
        assert len(timeouts) == 3
        assert clock[0] >= 10.1
        assert timeouts[1] < timeouts[0] and timeouts[2] < timeouts[1]

    asyncio.run(run())
