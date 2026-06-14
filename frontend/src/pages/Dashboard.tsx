import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

interface Repository {
  id: number;
  name: string;
  github_url: string;
  registered_at: string;
}

export default function Dashboard() {
  const [repositories, setRepositories] = useState<Repository[]>([]);

  useEffect(() => {
    api.get<Repository[]>('/repositories').then(res => setRepositories(res.data));
  }, []);

  return (
    <div className="container">
      <header>
        <h1>Dashboard</h1>
        <Link to="/register" className="btn btn-primary">Add Repository</Link>
      </header>
      
      <table className="table">
        <thead>
          <tr>
            <th>Repository Name</th>
            <th>GitHub URL</th>
            <th>Registered At</th>
          </tr>
        </thead>
        <tbody>
          {repositories.map(repo => (
            <tr key={repo.id}>
              <td><Link to={`/repositories/${repo.id}`}>{repo.name}</Link></td>
              <td><a href={repo.github_url} target="_blank" rel="noreferrer">{repo.github_url}</a></td>
              <td>{new Date(repo.registered_at).toLocaleString()}</td>
            </tr>
          ))}
          {repositories.length === 0 && (
            <tr>
              <td colSpan={3} style={{textAlign: "center"}}>No repositories registered yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
