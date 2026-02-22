import { useEffect, useState } from 'react';
import { checkAuth, login, logout } from './auth';
import UploadPage from './UploadPage';
import ResultsPage from './ResultsPage';

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    checkAuth().then((isAuth) => {
      if (!isAuth) {
        login();
      } else {
        setAuthenticated(true);
        setLoading(false);
      }
    });
  }, []);

  if (loading && !authenticated) {
    return (
      <div className="app">
        <main className="app-main">
          <p>Checking authentication…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Menu Vision</h1>
        <p className="app-tagline">AI-powered menu translator</p>
        <button className="logout-btn" onClick={() => logout()}>
          Log out
        </button>
      </header>
      <main className="app-main">
        {jobId ? (
          <ResultsPage jobId={jobId} onBack={() => setJobId(null)} />
        ) : (
          <UploadPage onJobCreated={setJobId} />
        )}
      </main>
    </div>
  );
}

export default App;
