import { Dialog } from '../components/ui/Dialog';
import { PageHeader } from '../components/ui/PageHeader';
import { useEffect, useState } from 'react';
import { UserPlus, Mail, ShieldAlert, Trash2, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/Button';
import { DEMO_MODE } from '../demo/transport';

interface Member {
  user_id: number;
  github_login: string;
  display_name: string | null;
  avatar_url: string | null;
  role: string;
  joined_at: string;
}

interface Invitation {
  id: number;
  role: string;
  invitee_github_login: string | null;
  invitee_email: string | null;
  status: string;
  expires_at: string;
  created_at: string;
}

const ROLES = ['ADMIN', 'MAINTAINER', 'REVIEWER', 'DEVELOPER'];

export function WorkspaceMembers() {
  const { activeWorkspace, user: currentUser } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Invite modal state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteRole, setInviteRole] = useState('DEVELOPER');
  const [inviteLogin, setInviteLogin] = useState('');
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  
  // The backend enforces true security.
  const isAdmin = activeWorkspace?.role === 'ADMIN';
  const canInvite = activeWorkspace?.role === 'ADMIN' || activeWorkspace?.role === 'MAINTAINER';
  const availableRoles = isAdmin ? ROLES : ROLES.filter(r => r !== 'ADMIN');

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch('http://127.0.0.1:8000/api/v1/workspaces/active/members', {
        credentials: 'include'
      });
      if (!res.ok) throw new Error('Failed to fetch members data');
      const data = await res.json();
      setMembers(data.members);
      setInvitations(data.invitations);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeWorkspace) {
      fetchData();
    }
  }, [activeWorkspace]);

  const handleCreateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    setError(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/v1/workspaces/active/invitations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          role: inviteRole,
          invitee_github_login: inviteLogin.trim() || null,
        })
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to create invitation');
      }
      
      const data = await res.json();
      // Assume frontend runs on same domain as current URL, or use a specific configured URL
      const link = `${window.location.origin}/invite/${data.token}`;
      setInviteLink(link);
      fetchData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setInviting(false);
    }
  };

  const handleRevokeInvite = async (invitationId: number) => {
    if (!confirm('Are you sure you want to revoke this invitation?')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/v1/workspaces/active/invitations/${invitationId}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (!res.ok) throw new Error('Failed to revoke invitation');
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleRoleChange = async (userId: number, newRole: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/v1/workspaces/active/members/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ role: newRole })
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to update role');
      }
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleRemoveMember = async (userId: number) => {
    if (!confirm(DEMO_MODE ? 'Remove this sample member in this browser? Reset demo restores them.' : 'Are you sure you want to remove this member from the workspace? They will lose access immediately.')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/v1/workspaces/active/members/${userId}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to remove member');
      }
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  if (loading && !showInviteModal) {
    return <div className="p-8 text-slate-500 font-medium">Loading members...</div>;
  }

  return (
    <div className="page-stack">
      <PageHeader title="Workspace Members" description={activeWorkspace?.name} actions={canInvite && <Button disabled={DEMO_MODE} title={DEMO_MODE ? 'Invitations require a configured live backend.' : undefined} onClick={() => setShowInviteModal(true)}><UserPlus size={16} />Invite Teammate</Button>} />
      {DEMO_MODE && <p className="alert">Try changing a sample role or removing a sample member. Changes stay in this browser. Sending invitations requires a configured live backend.</p>}
      
      {error && !showInviteModal && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {/* Members List */}
      <div className="table-wrapper">
        <table className="cg-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Joined</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.map(member => (
              <tr key={member.user_id}>
                <td>
                  <div className="flex items-center gap-3">
                    {member.avatar_url ? (
                      <img src={member.avatar_url} alt="" className="w-8 h-8 rounded-full border border-slate-200" />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center font-semibold text-white ">
                        {member.github_login.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-[var(--cg-text)]">
                        {member.display_name || member.github_login}
                        {member.user_id === currentUser?.id && (
                          <span className="ml-2 text-[10px] font-semibold bg-[var(--cg-surface-soft)] text-[var(--cg-muted)] border border-[var(--cg-border-soft)] px-2 py-0.5 rounded-full uppercase tracking-wider">You</span>
                        )}
                      </div>
                      <div className="text-[var(--cg-muted)] text-xs font-medium">@{member.github_login}</div>
                    </div>
                  </div>
                </td>
                <td>
                  {isAdmin && member.user_id !== currentUser?.id ? (
                    <select
                      aria-label={`Role for ${member.github_login}`}
                      value={member.role}
                      onChange={(e) => handleRoleChange(member.user_id, e.target.value)}
                      className="bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] text-[var(--cg-text)] font-medium text-sm rounded-lg focus:ring-4 focus:ring-blue-600/10 focus:border-blue-600 block px-3 py-1.5 outline-none transition-all"
                    >
                      {availableRoles.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  ) : (
                    <span className="badge badge--neutral">
                      {member.role}
                    </span>
                  )}
                </td>
                <td className="cell-muted">
                  {new Date(member.joined_at).toLocaleDateString()}
                </td>
                <td className="text-right">
                  {isAdmin && member.user_id !== currentUser?.id && (
                    <button 
                      onClick={() => handleRemoveMember(member.user_id)}
                      className="text-slate-400 hover:text-red-600 hover:bg-red-500/10 rounded-lg transition-colors p-2"
                      title="Remove member"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {/* Pending Invitations */}
      {canInvite && invitations.length > 0 && (
        <>
          <h3 className="text-lg font-semibold text-[var(--cg-text)] mb-2 mt-4 flex items-center gap-2">
            <Mail size={18} className="text-blue-500" />
            Pending Invitations
          </h3>
          <div className="table-wrapper">
            <table className="cg-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Role</th>
                  <th>Expires</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invitations.map(inv => (
                  <tr key={inv.id}>
                    <td className="font-medium text-[var(--cg-text)]">
                      {inv.invitee_github_login ? `@${inv.invitee_github_login}` : (inv.invitee_email || 'Anyone with link')}
                    </td>
                    <td>
                      <span className="px-2.5 py-1 rounded-md text-xs font-semibold tracking-wide bg-[var(--cg-surface-soft)] text-[var(--cg-text-secondary)] border border-[var(--cg-border-soft)]">
                        {inv.role}
                      </span>
                    </td>
                    <td className="cell-muted">
                      {new Date(inv.expires_at).toLocaleDateString()}
                    </td>
                    <td className="text-right">
                      <button 
                        onClick={() => handleRevokeInvite(inv.id)}
                        className="text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors px-3 py-1.5 text-sm font-semibold"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Invite Modal */}
      {showInviteModal && (
        <Dialog titleId="invite-title" onClose={() => { setShowInviteModal(false); setInviteLink(null); setError(null); }}>
            <button 
              onClick={() => {
                setShowInviteModal(false);
                setInviteLink(null);
                setError(null);
              }}
              className="icon-button modal-close" aria-label="Close invitation dialog"
            >
              <X size={20} />
            </button>
            
            <h2 id="invite-title">Invite Teammate</h2>
            
            {error && (
              <div className="alert alert--error mb-6" role="alert">
                {error}
              </div>
            )}
            
            {inviteLink ? (
              <div className="form-stack">
                <div className="bg-green-50 border border-green-200 text-green-700 p-4 rounded-md text-sm font-medium flex items-start gap-3 ">
                  <ShieldAlert size={18} className="mt-0.5 shrink-0 text-green-600" />
                  <p>Invitation created successfully. Share this link securely with your teammate.</p>
                </div>
                
                <div className="flex gap-2">
                  <input 
                    aria-label="Invitation link"
                    type="text"
                    readOnly 
                    value={inviteLink} 
                    className="min-w-0 flex-1 bg-slate-50 border border-slate-200 rounded-md px-4 py-3 text-sm text-slate-900 font-mono font-medium focus:outline-none focus:ring-4 focus:ring-blue-600/10 focus:border-blue-600 transition-all "
                    onClick={(e) => (e.target as HTMLInputElement).select()}
                  />
                  <Button 
                    onClick={() => {
                      navigator.clipboard.writeText(inviteLink);
                      alert('Link copied to clipboard!');
                    }}
                    variant="secondary"
                    className="shrink-0"
                  >
                    Copy
                  </Button>
                </div>
                
                <Button 
                  onClick={() => {
                    setShowInviteModal(false);
                    setInviteLink(null);
                  }}
                  className="w-full mt-2"
                >
                  Done
                </Button>
              </div>
            ) : (
              <form onSubmit={handleCreateInvite} className="form-stack">
                <div>
                  <label htmlFor="invite-login" className="block text-sm font-medium text-[var(--cg-text)] mb-2">
                    GitHub Username <span className="text-[var(--cg-muted)] font-medium">(Optional)</span>
                  </label>
                  <input id="invite-login"
                    type="text"
                    value={inviteLogin}
                    onChange={(e) => setInviteLogin(e.target.value)}
                    placeholder="e.g. octocat"
                    className="w-full bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] rounded-md px-4 py-3 text-[var(--cg-text)] font-medium placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-600/10 focus:border-blue-600 transition-all"
                  />
                  <p className="text-xs font-medium text-[var(--cg-muted)] mt-2">
                    If provided, only this GitHub user can accept the invitation.
                  </p>
                </div>
                
                <div>
                  <label htmlFor="invite-role" className="block text-sm font-medium text-[var(--cg-text)] mb-2">
                    Role
                  </label>
                  <select id="invite-role"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] rounded-md px-4 py-3 text-[var(--cg-text)] font-medium focus:outline-none focus:ring-4 focus:ring-blue-600/10 focus:border-blue-600 transition-all appearance-none"
                    style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: `right 0.5rem center`, backgroundRepeat: `no-repeat`, backgroundSize: `1.5em 1.5em`, paddingRight: `2.5rem` }}
                  >
                    {availableRoles.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                
                <div className="pt-6 flex justify-end gap-3">
                  <Button 
                    type="button" 
                    variant="ghost" 
                    onClick={() => setShowInviteModal(false)}
                    className="font-semibold text-[var(--cg-muted)] hover:text-[var(--cg-text)]"
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={inviting}>
                    {inviting ? 'Creating...' : 'Create Invite Link'}
                  </Button>
                </div>
              </form>
            )}
        </Dialog>
      )}
    </div>
  );
}
