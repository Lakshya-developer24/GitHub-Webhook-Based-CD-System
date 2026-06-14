import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';

interface Repository {
  id: number;
  name: string;
  github_url: string;
  webhook_url: string;
  webhook_secret: string;
  registered_at: string;
}

export default function RepositoryDetails() {
  const { id } = useParams<{ id: string }>();
  const [repo, setRepo] = useState<Repository | null>(null);
  const [deploymentCount, setDeploymentCount] = useState(0);
  const [latestStatus, setLatestStatus] = useState<string>('NONE');
  const [error, setError] = useState('');

  useEffect(() => {
    api.get<Repository>(`/repositories/${id}`)
      .then(res => setRepo(res.data))
      .catch(() => setError('Repository not found.'));
      
    api.get<any[]>(`/repositories/${id}/deployments`)
      .then(res => {
        setDeploymentCount(res.data.length);
        if (res.data.length > 0) {
          setLatestStatus(res.data[0].status);
        }
      })
      .catch(() => {});
  }, [id]);

  if (error) return <div className="container"><div className="alert alert-error">{error}</div><Link to="/">Back</Link></div>;
  if (!repo) return <div className="container">Loading...</div>;

  const webhookUrl = repo.webhook_url.startsWith('/') ? `${window.location.origin}${repo.webhook_url}` : repo.webhook_url;

  return (
    <div className="container">
      <header>
        <h1>Repository Details</h1>
        <Link to="/" className="btn">Back to Dashboard</Link>
      </header>
      
      <div className="card">
        <div className="detail-row">
          <strong>Repository Name:</strong> <span>{repo.name}</span>
        </div>
        <div className="detail-row">
          <strong>GitHub URL:</strong> <a href={repo.github_url} target="_blank" rel="noreferrer">{repo.github_url}</a>
        </div>
        <div className="detail-row">
          <strong>Webhook URL:</strong> <span>{webhookUrl}</span>
        </div>
        <div className="detail-row">
          <strong>Webhook Secret:</strong> <span>{repo.webhook_secret}</span>
        </div>
        <div className="detail-row">
          <strong>Registered At:</strong> <span>{new Date(repo.registered_at).toLocaleString()}</span>
        </div>
        <div className="detail-row">
          <strong>Latest Deployment:</strong>
          <span style={{
            marginRight: '1rem',
            padding: '4px 8px',
            borderRadius: '4px',
            backgroundColor: latestStatus === 'PENDING' ? '#fef3c7' : latestStatus === 'CLONING' ? '#e0e7ff' : latestStatus === 'RUNNING' ? '#dcfce7' : latestStatus === 'SUPERSEDED' ? '#e5e7eb' : '#eee',
            color: latestStatus === 'PENDING' ? '#92400e' : latestStatus === 'CLONING' ? '#3730a3' : latestStatus === 'RUNNING' ? '#166534' : latestStatus === 'SUPERSEDED' ? '#6b7280' : '#333'
          }}>
            {latestStatus}
          </span>
        </div>
        <div className="detail-row">
          <strong>Deployments:</strong> 
          <span style={{marginRight: '1rem'}}>{deploymentCount} total</span>
          <Link to={`/repositories/${repo.id}/deployments`} className="btn btn-primary" style={{padding: '0.25rem 0.5rem', fontSize: '0.875rem'}}>View History</Link>
        </div>
      </div>
    </div>
  );
}
