import React, { useState, useEffect } from 'react';
import { CodeGateAPI } from '../api/client';
import { Settings, Save } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { DEMO_MODE } from '../demo/transport';

interface TestingConfigurationProps {
  repositoryId: number;
}

export function TestingConfiguration({ repositoryId }: TestingConfigurationProps) {
  const { activeWorkspace } = useAuth();
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Read-only if Reviewer or Developer
  const canEdit = activeWorkspace?.role === 'ADMIN' || activeWorkspace?.role === 'MAINTAINER';

  useEffect(() => {
    CodeGateAPI.getTestingConfiguration(repositoryId)
      .then(data => {
        setConfig(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [repositoryId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;
    
    setSaving(true);
    setError(null);
    setSuccess(false);
    
    try {
      await CodeGateAPI.updateTestingConfiguration(repositoryId, config);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="skeleton skeleton--panel" />;

  return (
    <div className="dashboard-panel">
      <div className="dashboard-panel__head">
        <div className="dashboard-panel__title">
          <Settings size={18} strokeWidth={1.8} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
          Testing Configuration
        </div>
      </div>
      <div className="dashboard-panel__body">
        {error && (
          <div className="alert alert--error mb-4" role="alert">
            {error}
          </div>
        )}
        {success && (
          <div className="alert alert--success mb-4" role="status">
            {DEMO_MODE ? 'Sample configuration saved in this browser.' : 'Configuration saved successfully.'}
          </div>
        )}
        
        {DEMO_MODE && <p className="muted mb-4">Try these settings locally. Commands are sample configuration and will not execute in this demo.</p>}
        <form onSubmit={handleSave} className="form-stack">
          <div className="testing-toggles">
            <label className="flex items-center gap-2 text-sm font-medium text-foreground">
              <input 
                type="checkbox" 
                checked={config?.enabled || false}
                onChange={e => setConfig({...config, enabled: e.target.checked})}
                disabled={!canEdit || !config}
                
              />
              Enable Testing
            </label>
            <label className="flex items-center gap-2 text-sm font-medium text-foreground">
              <input 
                type="checkbox" 
                checked={config?.coverage_enabled || false}
                onChange={e => setConfig({...config, coverage_enabled: e.target.checked})}
                disabled={!canEdit || !config}
                
              />
              Enable Coverage Parsing
            </label>
            <label className="flex items-center gap-2 text-sm font-medium text-foreground">
              <input 
                type="checkbox" 
                checked={config?.network_enabled || false}
                onChange={e => setConfig({...config, network_enabled: e.target.checked})}
                disabled={!canEdit || !config}
                
              />
              Allow Network Access
            </label>
          </div>
          
          <div className="evidence-grid">
            <div>
              <label htmlFor="executor-type" className="block text-sm font-medium text-muted mb-1">Executor Type</label>
              <select id="executor-type" 
                value={config?.executor_type?.toUpperCase() || 'DISABLED'}
                onChange={e => setConfig({...config, executor_type: e.target.value})}
                disabled={!canEdit || !config}
                className="w-full"
              >
                <option value="DISABLED">Disabled</option>
                <option value="LOCAL_TRUSTED">Local Trusted (Warning: Unsafe)</option>
                <option value="DOCKER">Docker Isolated (Recommended)</option>
              </select>
            </div>
            
            <div>
              <label htmlFor="docker-image" className="block text-sm font-medium text-muted mb-1">Docker Image</label>
              <input id="docker-image" 
                type="text" 
                value={config?.docker_image || ''}
                onChange={e => setConfig({...config, docker_image: e.target.value})}
                disabled={!canEdit || !config}
                placeholder="e.g. python:3.12-slim"
                className="w-full"
              />
            </div>
          </div>
          
          <div className="evidence-grid">
            <div>
              <label htmlFor="install-command" className="block text-sm font-medium text-muted mb-1">Install Command</label>
              <input id="install-command" 
                type="text" 
                value={config?.install_command || ''}
                onChange={e => setConfig({...config, install_command: e.target.value})}
                disabled={!canEdit || !config}
                placeholder="e.g. pip install -r requirements.txt"
                className="w-full"
              />
            </div>
            
            <div>
              <label htmlFor="test-command" className="block text-sm font-medium text-muted mb-1">Test Command</label>
              <input id="test-command" 
                type="text" 
                value={config?.test_command || ''}
                onChange={e => setConfig({...config, test_command: e.target.value})}
                disabled={!canEdit || !config}
                placeholder="e.g. pytest"
                className="w-full"
              />
            </div>
          </div>
          
          {canEdit && (
            <div className="pt-2">
              <button 
                type="submit" 
                disabled={saving || !config}
                className="btn-primary"
              >
                <Save size={16} />
                {saving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
