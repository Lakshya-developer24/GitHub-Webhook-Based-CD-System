import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RepositoryRegistration from './pages/RepositoryRegistration';
import RepositoryDetails from './pages/RepositoryDetails';

function App() {
  return (
    <BrowserRouter>
      <nav className="navbar">
        <div className="navbar-brand">GitOps CD Platform</div>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/register" element={<RepositoryRegistration />} />
          <Route path="/repositories/:id" element={<RepositoryDetails />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
