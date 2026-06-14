import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';

interface Deployment {
  id: number;
  commit_sha: string;
  status: string;
  started_at: string | null;
  triggered_by: string;
}

interface Repository {
  name: string;
}

export default function DeploymentHistory() {
  const { id } = useParams<{ id: string }>();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);

  useEffect(() => {
    api.get<Repository>(`/repositories/${id}`).then(res => setRepo(res.data)).catch(() => {});
    
    const fetchDeployments = () => {
      api.get<Deployment[]>(`/repositories/${id}/deployments`).then(res => setDeployments(res.data)).catch(() => {});
    };
    
    fetchDeployments();
    const intervalId = setInterval(fetchDeployments, 3000);
    
    return () => clearInterval(intervalId);
  }, [id]);

  return (
    <div className="container">
      <header>
        <h1>Deployments: {repo ? repo.name : '...'}</h1>
        <Link to={`/repositories/${id}`} className="btn">Back to Repository</Link>
      </header>

      <table className="table">
        <thead>
          <tr>
            <th>Deployment ID</th>
            <th>Commit SHA</th>
            <th>Status</th>
            <th>Delivery ID</th>
          </tr>
        </thead>
        <tbody>
          {deployments.map(dep => (
            <tr key={dep.id}>
              <td>{dep.id}</td>
              <td>{dep.commit_sha ? dep.commit_sha.substring(0, 7) : 'N/A'}</td>
              <td>
                <span style={{
                  padding: '4px 8px', 
                  borderRadius: '4px',
                  backgroundColor: dep.status === 'PENDING' ? '#fef3c7' : '#eee',
                  color: dep.status === 'PENDING' ? '#92400e' : '#333'
                }}>
                  {dep.status}
                </span>
              </td>
              <td>{dep.triggered_by ? dep.triggered_by.substring(0, 8) + '...' : ''}</td>
            </tr>
          ))}
          {deployments.length === 0 && (
            <tr>
              <td colSpan={4} style={{textAlign: "center"}}>No deployments found.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
