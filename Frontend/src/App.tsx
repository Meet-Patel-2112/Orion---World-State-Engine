import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { SignIn } from './pages/SignIn';
import { Worlds } from './pages/Worlds';
import { NewWorld } from './pages/NewWorld';
import { ProcessingWorld } from './pages/ProcessingWorld';
import { WorldHome } from './pages/WorldHome';
import { Manuscripts } from './pages/Manuscripts';
import { WritingRoom } from './pages/WritingRoom';
import { EntityLedger } from './pages/EntityLedger';
import { WorldGraph } from './pages/WorldGraph';
import { WorldTimeline } from './pages/WorldTimeline';
import { Contradictions } from './pages/Contradictions';
import { WorldAssistant } from './pages/WorldAssistant';
import { useAuthStore } from './store/useAuthStore';
import { ProtectedRoute, PublicOnlyRoute } from './components/ProtectedRoute';

const App: React.FC = () => {
  const checkAuth = useAuthStore((state) => state.checkAuth);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Auth Routes */}
        <Route 
          path="/signin" 
          element={
            <PublicOnlyRoute>
              <SignIn />
            </PublicOnlyRoute>
          } 
        />
        
        {/* Protected World Routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="/worlds" element={<Worlds />} />
          <Route path="/worlds/new" element={<NewWorld />} />
          
          <Route path="/worlds/:worldId" element={<WorldHome />} />
          <Route path="/worlds/:worldId/processing" element={<ProcessingWorld />} />
          <Route path="/worlds/:worldId/manuscripts" element={<Manuscripts />} />
          <Route path="/worlds/:worldId/manuscripts/:manuscriptId" element={<WritingRoom />} />
          <Route path="/worlds/:worldId/world" element={<EntityLedger />} />
          <Route path="/worlds/:worldId/graph" element={<WorldGraph />} />
          <Route path="/worlds/:worldId/timeline" element={<WorldTimeline />} />
          <Route path="/worlds/:worldId/contradictions" element={<Contradictions />} />
          <Route path="/worlds/:worldId/assistant" element={<WorldAssistant />} />
        </Route>

        {/* Fallbacks */}
        <Route path="/" element={<Navigate to="/worlds" replace />} />
        <Route path="*" element={<Navigate to="/worlds" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;

