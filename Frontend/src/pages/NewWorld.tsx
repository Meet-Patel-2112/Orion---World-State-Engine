import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';

export const NewWorld: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setActiveWorld } = useWorldStore();
  const [worldName, setWorldName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processFileUpload = async (file: File) => {
    setLoading(true);
    setError(null);

    const filenameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
    const nameToUse = worldName.trim() || filenameWithoutExt || 'Extracted World';
    const descToUse = description.trim() || `World extracted from uploaded manuscript ${file.name}.`;

    try {
      // Step 1: Create world
      const worldData = await apiFetch<any>('/worlds', {
        method: 'POST',
        body: JSON.stringify({ name: nameToUse, description: descToUse })
      });

      setActiveWorld(worldData.id);

      // Step 2: Upload manuscript file
      const formData = new FormData();
      formData.append('file', file);

      const manuscriptRes = await apiFetch<any>(`/worlds/${worldData.id}/manuscripts`, {
        method: 'POST',
        body: formData
      });

      // Step 3: Redirect to processing view with job_id
      if (manuscriptRes.job_id) {
        navigate(`/worlds/${worldData.id}/processing?jobId=${manuscriptRes.job_id}`);
      } else {
        navigate(`/worlds/${worldData.id}`);
      }
    } catch (e: any) {
      console.error("Failed to upload manuscript via API", e);
      setError(e.message || "Failed to upload manuscript file");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFileUpload(e.target.files[0]);
    }
  };

  const handleStartImport = async (mode: string) => {
    if (mode === 'manuscript' || mode === 'notes') {
      fileInputRef.current?.click();
      return;
    }

    setLoading(true);
    setError(null);

    const nameToUse = worldName.trim() || 'New Chronicle';
    const descToUse = description.trim() || 'A blank canvas initialized in the archives. Add characters, locations, and facts manually.';

    try {
      const data = await apiFetch<any>('/worlds', {
        method: 'POST',
        body: JSON.stringify({ name: nameToUse, description: descToUse })
      });

      setActiveWorld(data.id);
      navigate(`/worlds/${data.id}`);
    } catch (e: any) {
      console.error("Failed to create world via API", e);
      setError(e.message || "Failed to create world");
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFileUpload(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="bg-void-black text-on-background min-h-screen w-full font-body-md selection:bg-primary/30 selection:text-primary-fixed flex flex-col items-center justify-center overflow-x-hidden select-none relative">
      
      {/* Hidden File Input */}
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        accept=".txt,.pdf,.docx,.epub" 
        className="hidden" 
      />

      {/* Background Noise Texture */}
      <div className="fixed inset-0 pointer-events-none opacity-5 mix-blend-overlay z-0" style={{ backgroundImage: "url('data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.65%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E')" }}></div>
      
      <main className="relative z-10 w-full max-w-4xl px-gutter py-12 flex flex-col items-center animate-fade-in-up">
        
        {/* Header */}
        <header className="text-center mb-stack-lg max-w-2xl mx-auto flex flex-col gap-2">
          <h1 className="font-headline-lg text-headline-lg md:font-display-lg md:text-display-lg text-starlight-white tracking-tight">Create World</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-lg mx-auto">
            Bring what you already have. You don't have to build your world from zero.
          </p>
        </header>

        {error && (
          <div className="mb-6 w-full max-w-md p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs text-center">
            {error}
          </div>
        )}

        {/* Custom Name / Details Form */}
        <div className="w-full max-w-lg mb-8 space-y-4">
          <div>
            <label className="block text-xs font-label-sm text-on-surface-variant/70 mb-1 uppercase tracking-wider">World Name</label>
            <input 
              type="text" 
              value={worldName}
              onChange={(e) => setWorldName(e.target.value)}
              placeholder="e.g. Chronicle of Aethelgard"
              className="w-full bg-surface-container-low border border-starlight-white/10 rounded p-3 text-starlight-white text-sm focus:outline-none focus:border-copper-glow"
            />
          </div>
          <div>
            <label className="block text-xs font-label-sm text-on-surface-variant/70 mb-1 uppercase tracking-wider">Description (Optional)</label>
            <textarea 
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief summary of the world's lore..."
              rows={2}
              className="w-full bg-surface-container-low border border-starlight-white/10 rounded p-3 text-starlight-white text-sm focus:outline-none focus:border-copper-glow resize-none"
            />
          </div>
        </div>

        {/* Options Grid */}
        <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6 mt-2">
          
          {/* Option 1: Import Manuscript */}
          <button 
            disabled={loading}
            onClick={() => handleStartImport('manuscript')}
            className="group flex flex-col items-center text-center p-8 rounded-xl bg-surface-container-low border border-outline-variant/30 hover:border-primary/50 transition-all duration-300 relative overflow-hidden focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          >
            <div className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <div className="w-16 h-16 rounded-full bg-surface-container-high flex items-center justify-center mb-6 group-hover:bg-primary/10 transition-colors duration-300 border border-outline-variant/50 group-hover:border-primary/30">
              <span className="material-symbols-outlined text-3xl text-on-surface group-hover:text-primary transition-colors font-light">menu_book</span>
            </div>
            <h3 className="font-headline-md text-headline-md text-starlight-white mb-2">Import a Manuscript</h3>
            <p className="font-body-md text-body-md text-on-surface-variant/70 text-sm">
              Start by extracting lore and entities directly from your text.
            </p>
          </button>

          {/* Option 2: Import World Material */}
          <button 
            disabled={loading}
            onClick={() => handleStartImport('notes')}
            className="group flex flex-col items-center text-center p-8 rounded-xl bg-surface-container-low border border-primary/30 shadow-[0_0_40px_rgba(254,182,141,0.03)] hover:border-primary transition-all duration-300 relative overflow-hidden md:-translate-y-4 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          >
            <div className="absolute inset-0 bg-gradient-to-b from-primary/10 to-transparent opacity-100 transition-opacity duration-500"></div>
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1/3 h-px bg-gradient-to-r from-transparent via-primary to-transparent opacity-50"></div>
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6 border border-primary/30 group-hover:bg-primary/20 transition-colors">
              <span className="material-symbols-outlined text-3xl text-primary font-light">folder_zip</span>
            </div>
            <h3 className="font-headline-md text-headline-md text-starlight-white mb-2">Import World Material</h3>
            <p className="font-body-md text-body-md text-on-surface-variant/70 text-sm">
              Bring in your notes, maps, and existing encyclopedias.
            </p>
            <div className="mt-6 flex gap-3 text-on-surface-variant/50 text-[10px] font-label-sm">
              <span className="border border-outline-variant/30 px-2 py-0.5 rounded bg-surface-container">TXT</span>
              <span className="border border-outline-variant/30 px-2 py-0.5 rounded bg-surface-container">PDF</span>
              <span className="border border-outline-variant/30 px-2 py-0.5 rounded bg-surface-container">EPUB</span>
              <span className="material-symbols-outlined text-base font-light self-center">image</span>
            </div>
          </button>

          {/* Option 3: Scratch */}
          <button 
            disabled={loading}
            onClick={() => handleStartImport('scratch')}
            className="group flex flex-col items-center text-center p-8 rounded-xl bg-surface-container-low border border-outline-variant/30 hover:border-outline transition-all duration-300 relative overflow-hidden focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          >
            <div className="w-16 h-16 rounded-full bg-surface-container-high flex items-center justify-center mb-6 group-hover:bg-surface-container-highest transition-colors duration-300 border border-outline-variant/50">
              <span className="material-symbols-outlined text-3xl text-on-surface-variant font-light">add</span>
            </div>
            <h3 className="font-headline-md text-headline-md text-starlight-white mb-2">Start from Scratch</h3>
            <p className="font-body-md text-body-md text-on-surface-variant/70 text-sm">
              Begin with a blank canvas and build entity by entity.
            </p>
          </button>

        </div>

        {/* Drag and Drop Area */}
        <div 
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => !loading && fileInputRef.current?.click()}
          className="w-full mt-12 p-12 border border-dashed border-outline-variant/50 rounded-xl bg-surface-container-lowest/50 flex flex-col items-center justify-center transition-colors hover:bg-surface-container-low/50 hover:border-primary/50 group cursor-pointer relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
          <span className="material-symbols-outlined text-4xl text-outline mb-4 group-hover:text-primary transition-colors font-light">upload_file</span>
          <p className="font-body-lg text-body-lg text-starlight-white mb-1">
            {loading ? 'Uploading & initializing extraction...' : 'Drag and drop your manuscript here'}
          </p>
          <p className="font-body-md text-body-md text-on-surface-variant/60 text-sm">
            or click to browse from your computer (.txt, .pdf, .docx)
          </p>
        </div>

        {/* Cancel Button */}
        <button 
          onClick={() => navigate('/worlds')} 
          className="mt-8 text-on-surface-variant/60 hover:text-primary transition-colors flex items-center gap-1 font-label-sm text-xs uppercase tracking-wider"
        >
          <span className="material-symbols-outlined text-sm font-light">arrow_back</span>
          Back to Archives
        </button>

      </main>
    </div>
  );
};
