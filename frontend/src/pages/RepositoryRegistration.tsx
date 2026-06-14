import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

interface RegistrationResponse {
  webhook_url: string;
  webhook_secret: string;
}

export default function RepositoryRegistration() {
  const [name, setName] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [error, setError] = useState('');
  const [successData, setSuccessData] = useState<RegistrationResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    try {
      const res = await api.post('/repositories', { name, github_url: githubUrl });
      // Build absolute webhook URL if it's relative
      let webhookUrl = res.data.webhook_url;
      if (webhookUrl.startsWith('/')) {
        webhookUrl = `${window.location.origin}${webhookUrl}`;
      }
      setSuccessData({
        ...res.data,
        webhook_url: webhookUrl
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during registration.');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  if (successData) {
    return (
      <div className="container">
        <h1>Registration Successful</h1>
        <div className="card">
          <p>Please configure this webhook in your GitHub repository settings.</p>
          
          <div className="field">
            <label>Webhook URL</label>
            <div className="copy-group">
              <input type="text" readOnly value={successData.webhook_url} />
              <button type="button" onClick={() => copyToClipboard(successData.webhook_url)} className="btn">Copy</button>
            </div>
          </div>

          <div className="field">
            <label>Webhook Secret</label>
            <div className="copy-group">
              <input type="text" readOnly value={successData.webhook_secret} />
              <button type="button" onClick={() => copyToClipboard(successData.webhook_secret)} className="btn">Copy</button>
            </div>
          </div>
          
          <div className="mt-4">
            <Link to="/" className="btn btn-primary">Back to Dashboard</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <header>
        <h1>Add Repository</h1>
        <Link to="/" className="btn">Cancel</Link>
      </header>

      <div className="card">
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Repository Name</label>
            <input 
              type="text" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder="e.g., my-awesome-app"
              required 
            />
          </div>
          <div className="form-group">
            <label>GitHub URL</label>
            <input 
              type="url" 
              value={githubUrl} 
              onChange={e => setGithubUrl(e.target.value)} 
              placeholder="https://github.com/user/repo"
              required 
            />
          </div>
          <button type="submit" className="btn btn-primary">Submit</button>
        </form>
      </div>
    </div>
  );
}
