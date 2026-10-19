import { useState } from 'react';
import { FlaskConical, HelpCircle, RotateCcw, ExternalLink, Play, X } from 'lucide-react';
import { Dialog } from '../components/ui/Dialog';
import { activeDemo } from './transport';

export function DemoBanner() {
  const [help, setHelp] = useState(false);
  const [reset, setReset] = useState(false);
  return <>
    <section className="demo-banner" aria-label="Interactive demo information">
      <div className="demo-banner__label"><FlaskConical size={20} /><div><strong>Interactive demo</strong><span>Sample data · Changes stay in this browser</span></div></div>
      <div className="demo-banner__actions">
        <a href="/recordings/codegate-runtime-vi.mp4" target="_blank" rel="noreferrer"><Play size={14} />Watch real runtime</a>
        <a href="https://github.com/NV-DuyManh/CodeGate" target="_blank" rel="noreferrer">Source<ExternalLink size={13} /></a>
        <button onClick={() => setHelp(true)} aria-label="Demo help"><HelpCircle size={15} />Help</button>
        <button onClick={() => setReset(true)}><RotateCcw size={14} />Reset demo</button>
      </div>
    </section>
    {help && <Dialog titleId="demo-help-title" onClose={() => setHelp(false)}>
      <button className="icon-button modal-close" onClick={() => setHelp(false)} aria-label="Close help"><X size={20} /></button>
      <h2 id="demo-help-title">Explore the CodeGate demo</h2>
      <div className="form-stack">
        <p>Explore two sample workspaces, search and filter pull requests, inspect quality and policy evidence, and mark coaching lessons as understood.</p>
        <p>Repository testing settings, member changes and lesson progress are saved only in this browser. Reset demo restores the original sample.</p>
        <p>All dashboard metrics, findings and recommendations are illustrative fixtures. GitHub OAuth, installations, sync, invitations, AI reviews and test execution require a configured live backend and are unavailable here.</p>
        <p>The separate runtime video shows a real local backend, database, static analysis and test execution. It does not demonstrate a connected GitHub installation or AI provider.</p>
        <a className="btn-primary" href="/recordings/codegate-runtime-vi.mp4" target="_blank" rel="noreferrer"><Play size={16} />Watch real runtime</a>
      </div>
    </Dialog>}
    {reset && <Dialog titleId="demo-reset-title" onClose={() => setReset(false)}>
      <h2 id="demo-reset-title">Reset this demo?</h2>
      <p>Your local settings, member changes and lesson progress will be replaced with the original sample data.</p>
      <div className="flex gap-3 mt-6 justify-end"><button className="btn-secondary" onClick={() => setReset(false)}>Keep exploring</button><button className="btn-primary" onClick={() => { activeDemo?.reset(); window.location.assign('/dashboard'); }}>Reset sample data</button></div>
    </Dialog>}
  </>;
}
