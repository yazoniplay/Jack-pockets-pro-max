import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowDownToLine, ArrowRight, Check, Clapperboard,
  FileVideo2, Film, FolderOpen, LoaderCircle, Mic2, Plus, Radio,
  RefreshCw, Search, Settings2, ShieldCheck, Sparkles, WandSparkles,
} from "lucide-react";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type EventItem = { type: string; created_at: string; payload: Record<string, unknown> };
type Asset = {
  provider_id: string; title: string; creator: string; source_url: string;
  local_file: string; width: number; height: number; duration_seconds: number;
  license_name: string; license_url: string; beat_id?: string | null;
};
type Candidate = {
  provider_id: string; title: string; creator: string; page_url: string;
  download_url: string; width: number; height: number; duration_seconds: number;
  quality_score: number; quality_notes: string[]; search_position: number;
};
type Job = {
  id: string; status: string; brief: { topic: string; target_minutes: number; language: string };
  created_at: string; updated_at: string; result: Record<string, any> | null;
  error: string | null; events: EventItem[];
};
type Provider = { name: string; configured: boolean; model: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload as T;
}

const prettyStatus = (status: string) => status.replaceAll("_", " ");
const frameTime = (frame: number, fps: number) => {
  const seconds = Math.floor(frame / fps);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
};
const dateLabel = (value: string) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [collaborationReady, setCollaborationReady] = useState(false);
  const [topic, setTopic] = useState("");
  const [minutes, setMinutes] = useState(12);
  const [language, setLanguage] = useState("en");
  const [tone, setTone] = useState("Cinematic, evidence-led");
  const [script, setScript] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeBeatId, setActiveBeatId] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [beatRecommendations, setBeatRecommendations] = useState<Record<string, Candidate[]>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = useMemo(() => jobs.find((job) => job.id === selectedId) || null, [jobs, selectedId]);
  const result = selected?.result || {};
  const assets: Asset[] = result.assets || [];
  const storyboard = result.storyboard;
  const coveredBeats = storyboard?.beats?.filter((beat: any) => assets.some((asset) => asset.beat_id === beat.id)).length || 0;
  const narration = result.narration;
  const synthesis = result.synthesis || "";
  const scriptReview = result.script_review || "";
  const scriptWordCount = script.trim() ? script.trim().split(/\s+/).length : 0;
  const estimatedScriptMinutes = scriptWordCount / 135;

  const refresh = useCallback(async () => {
    try {
      const [jobList, providerState] = await Promise.all([
        request<Job[]>("/api/jobs"),
        request<{ providers: Provider[]; collaboration_ready: boolean }>("/api/providers"),
      ]);
      setJobs(jobList);
      setProviders(providerState.providers);
      setCollaborationReady(providerState.collaboration_ready);
      if (!selectedId && jobList.length) setSelectedId(jobList[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect to the API.");
    }
  }, [selectedId]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    setScript(result.script_draft || "");
    setCandidates([]);
    setBeatRecommendations({});
    setActiveBeatId("");
    setNotice("");
  }, [selectedId, synthesis, result.script_draft]);

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The action failed.");
    } finally {
      setBusy("");
    }
  };

  const createProject = () => run("create", async () => {
    if (topic.trim().length < 3) throw new Error("Enter a documentary topic first.");
    const job = await request<Job>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        brief: { topic, target_minutes: minutes, language, tone, audience: "General audience" },
      }),
    });
    setSelectedId(job.id);
    await request(`/api/jobs/${job.id}/run`, { method: "POST" });
    setTopic("");
    setNotice("Documentary brief created. The AI roundtable has started.");
  });

  const generateNarration = () => {
    if (!selected) return;
    void run("narration", async () => {
      if (script.trim().length < 20) throw new Error("Review and enter a complete narration script.");
      await request(`/api/jobs/${selected.id}/narration`, {
        method: "POST",
        body: JSON.stringify({ text: script, voice: "en-US-AriaNeural", fps: 30 }),
      });
      setNotice("Narration generation started.");
    });
  };

  const searchFootage = (query = searchQuery, beatId = "") => {
    void run("search", async () => {
      if (!query.trim()) throw new Error("Enter a footage search phrase.");
      setSearchQuery(query);
      setActiveBeatId(beatId);
      const beat = storyboard?.beats?.find((item: any) => item.id === beatId);
      const targetDuration = beat
        ? Math.max(1, Math.ceil((beat.end_frame - beat.start_frame) / storyboard.fps))
        : null;
      const durationParam = targetDuration ? `&target_duration_seconds=${targetDuration}` : "";
      const data = await request<{ results: Candidate[] }>(
        `/api/assets/search?query=${encodeURIComponent(query)}&limit=12${durationParam}`,
      );
      setCandidates(data.results);
      setNotice(`${data.results.length} footage options found.`);
    });
  };

  const recommendAllFootage = () => {
    if (!selected || !storyboard?.beats?.length) return;
    void run("recommend", async () => {
      const data = await request<{ recommendations: Array<{ beat_id: string; results: Candidate[]; error: string | null }>; searched_beats: number; beats_with_results: number }>("/api/jobs/" + selected.id + "/assets/recommendations", { method: "POST" });
      setBeatRecommendations(Object.fromEntries(data.recommendations.map((item) => [item.beat_id, item.results])));
      setNotice("Found footage options for " + data.beats_with_results + " of " + data.searched_beats + " storyboard beats.");
    });
  };

  const addAsset = (candidate: Candidate, beatId = activeBeatId) => {
    if (!selected) return;
    void run(`asset-${candidate.provider_id}`, async () => {
      await request(`/api/jobs/${selected.id}/assets`, {
        method: "POST",
        body: JSON.stringify({
          provider_id: candidate.provider_id,
          title: candidate.title,
          creator: candidate.creator,
          page_url: candidate.page_url,
          media_uri: candidate.download_url,
          width: candidate.width,
          height: candidate.height,
          duration_seconds: candidate.duration_seconds,
          beat_id: beatId || null,
        }),
      });
      setNotice("Footage downloaded and its source/license metadata recorded.");
    });
  };

  const renderVideo = () => {
    if (!selected || !narration?.audio_path) return;
    void run("render", async () => {
      if (!assets.length) throw new Error("Add at least one footage clip before rendering.");
      const storyboard = result.storyboard;
      let scenes: Record<string, unknown>[];
      if (storyboard?.beats?.length) {
        const assignments = storyboard.beats.map((beat: any) => ({
          beat,
          asset: assets.find((asset) => asset.beat_id === beat.id),
        }));
        const missing = assignments.filter((item: any) => !item.asset);
        if (missing.length) {
          throw new Error(`The storyboard has ${missing.length} uncovered visual beats. Add one clip to every storyboard beat before rendering.`);
        }
        scenes = assignments.map(({ beat, asset }: any, index: number) => ({
          id: beat.id,
          kind: "footage",
          duration_frames: beat.end_frame - beat.start_frame,
          eyebrow: index === 0 ? "A JACK POCKETS DOCUMENTARY" : beat.shot_type.toUpperCase(),
          title: beat.visual_description,
          body: "",
          asset: {
            source_url: asset.source_url,
            local_file: asset.local_file,
            title: asset.title,
            creator: asset.creator,
            license_name: asset.license_name,
            license_url: asset.license_url,
            attribution_required: false,
          },
        }));
      } else {
        const introFrames = 150;
        const footageFrames = assets.reduce((sum, asset) => sum + asset.duration_seconds * 30, 0);
        if (introFrames + footageFrames < narration.duration_frames) {
          throw new Error(`Selected footage covers ${Math.round(footageFrames / 30)} seconds, but narration needs about ${Math.round(narration.duration_frames / 30)} seconds. Add more unique clips before rendering.`);
        }
        scenes = [
          {
            id: "opening-title",
            kind: "title",
            duration_frames: introFrames,
            eyebrow: "A JACK POCKETS DOCUMENTARY",
            title: selected.brief.topic,
            body: "An evidence-led documentary",
          },
          ...assets.map((asset, index) => ({
            id: `footage-${index + 1}`,
            kind: "footage",
            duration_frames: Math.max(15, asset.duration_seconds * 30),
            title: asset.title,
            body: asset.creator ? `Footage: ${asset.creator}` : "",
            asset: {
              source_url: asset.source_url,
              local_file: asset.local_file,
              title: asset.title,
              creator: asset.creator,
              license_name: asset.license_name,
              license_url: asset.license_url,
              attribution_required: false,
            },
          })),
        ];
      }
      const manifest = {
        title: selected.brief.topic,
        fps: 30,
        width: 1920,
        height: 1080,
        narration_file: narration.audio_path,
        scenes,
        captions: narration.captions,
      };
      await request(`/api/jobs/${selected.id}/render`, {
        method: "POST",
        body: JSON.stringify(manifest),
      });
      setNotice("Remotion render started. Quality checks will run before completion.");
    });
  };


  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Clapperboard size={19} /></div>
          <div><strong>JACK POCKETS</strong><span>PRO MAX / STUDIO</span></div>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="nav-item selected"><Film size={17} /> Documentary studio</button>
        <button className="nav-item" onClick={() => void refresh()}><FolderOpen size={17} /> Projects <span className="nav-count">{jobs.length}</span></button>
        <div className="sidebar-bottom">
          <div className="connection-card">
            <div className="connection-heading"><span className="status-dot" /> API CONNECTION</div>
            <span className="connection-url">{API.replace(/^https?:\/\//, "")}</span>
            <button onClick={() => void refresh()}><RefreshCw size={13} /> Refresh status</button>
          </div>
          <div className="user-chip"><div className="avatar">JP</div><div><strong>Production workspace</strong><span>Local development</span></div><Settings2 size={16} /></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs">Studio <span>/</span> Documentary generator</div>
          <div className="topbar-right"><span className="live-indicator"><i /> SYSTEM LIVE</span><span className="version">BUILD 0.2.0</span></div>
        </header>

        <div className="page-wrap">
          <section className="page-heading">
            <div><div className="eyebrow"><Sparkles size={13} /> AI DOCUMENTARY PRODUCTION</div><h1>Documentary studio</h1><p>From a research brief to a rendered, quality-checked film.</p></div>
            <div className="heading-status"><span className="status-dot" /> Pipeline online</div>
          </section>

          <section className="provider-strip">
            <div className="provider-title"><Radio size={15} /><span>MODEL NETWORK</span></div>
            {["anthropic", "gemini", "openai"].map((name) => {
              const provider = providers.find((item) => item.name === name);
              return <div className="provider-pill" key={name}><span className={provider ? "provider-light on" : "provider-light"} />{name === "anthropic" ? "Claude" : name === "gemini" ? "Gemini" : "OpenAI"}<small>{provider ? "KEY CONFIGURED" : "NOT CONFIGURED"}</small></div>;
            })}
            <div className={collaborationReady ? "network-state ready" : "network-state"}>{collaborationReady ? <Check size={14} /> : <Activity size={14} />}{collaborationReady ? "Multi-agent configured" : "Add 2+ API keys"}</div>
          </section>

          {error && <div className="alert error"><ShieldCheck size={16} />{error}<button onClick={() => setError("")}>Dismiss</button></div>}
          {notice && <div className="alert success"><Check size={16} />{notice}<button onClick={() => setNotice("")}>Dismiss</button></div>}

          <div className="studio-grid">
            <section className="panel brief-panel">
              <div className="panel-header"><div><span className="step-number">01</span><div><h2>New documentary</h2><p>Define the production brief</p></div></div><span className="panel-icon"><WandSparkles size={17} /></span></div>
              <label>DOCUMENTARY TOPIC</label>
              <textarea value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. The hidden history of the Silk Road" rows={3} />
              <div className="field-row">
                <div className="field"><label>TARGET LENGTH</label><select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}><option value={5}>5 minutes</option><option value={8}>8 minutes</option><option value={12}>12 minutes</option><option value={15}>15 minutes</option><option value={20}>20 minutes</option><option value={30}>30 minutes</option></select></div>
                <div className="field"><label>LANGUAGE</label><select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">English</option><option value="sv">Swedish</option><option value="ar">Arabic</option><option value="es">Spanish</option><option value="fr">French</option></select></div>
              </div>
              <label>EDITORIAL DIRECTION</label>
              <select value={tone} onChange={(e) => setTone(e.target.value)}><option>Cinematic, evidence-led</option><option>Investigative journalism</option><option>Historical documentary</option><option>Explainer, accessible</option><option>Dark, atmospheric</option></select>
              <button className="primary-button" disabled={!!busy || topic.trim().length < 3} onClick={createProject}>{busy === "create" ? <LoaderCircle className="spin" size={17} /> : <Plus size={17} />} Create production brief <ArrowRight size={16} /></button>
              <div className="fine-print"><ShieldCheck size={13} /> AI planning starts only when you create the job. Provider usage may incur API charges.</div>
            </section>

            <section className="panel project-panel">
              <div className="panel-header"><div><span className="step-number">02</span><div><h2>Production queue</h2><p>Track active and completed films</p></div></div><button className="icon-button" onClick={() => void refresh()}><RefreshCw size={15} /></button></div>
              {jobs.length === 0 ? <div className="empty-state"><div className="empty-icon"><FileVideo2 size={24} /></div><strong>No productions yet</strong><span>Your documentary jobs will appear here.</span></div> : <div className="job-list">{jobs.map((job) => <button key={job.id} className={selectedId === job.id ? "job-row active" : "job-row"} onClick={() => setSelectedId(job.id)}><div className="job-thumb"><Clapperboard size={17} /></div><div className="job-meta"><strong>{job.brief.topic}</strong><span>{dateLabel(job.created_at)} · {job.brief.target_minutes} min</span></div><span className={`job-status ${job.status}`}>{prettyStatus(job.status)}</span></button>)}</div>}
            </section>
          </div>

          {selected && <section className="panel pipeline-panel">
            <div className="panel-header"><div><span className="step-number">03</span><div><h2>Production pipeline</h2><p>{selected.brief.topic}</p></div></div><span className={`job-status large ${selected.status}`}>{prettyStatus(selected.status)}</span></div>
            <div className="pipeline-steps">
              {[
                ["AI roundtable", "Parallel research, story architecture and fact review", "needs_review"],
                ["Narration", "Approved script, voice generation and timed captions", "narrating"],
                ["Footage", "Source-aware stock footage selection", "assets"],
                ["Rendering", "Remotion composition and FFprobe quality gate", "rendering"],
              ].map(([name, description, stage], index) => <div className="pipeline-step" key={name}><div className={selected.status === stage || (index === 0 && selected.result?.synthesis) || (index === 1 && narration) || (index === 2 && assets.length) || (index === 3 && selected.status === "completed") ? "step-icon done" : "step-icon"}>{index + 1}</div><div><strong>{name}</strong><span>{description}</span></div></div>)}
            </div>
            {selected.status === "failed" && <div className="failed-stage"><div className="inline-error">{selected.error || "The pipeline failed. Check the job event history."}</div><button className="secondary-button" disabled={!!busy} onClick={() => void run("retry", async () => { await request(`/api/jobs/${selected.id}/run`, { method: "POST" }); setNotice("Planning retry started."); })}>{busy === "retry" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} Retry AI planning</button></div>}
            {synthesis && <div className="review-block"><div className="subheading"><span>AI EDITORIAL SYNTHESIS</span><span className="review-tag">REVIEW REQUIRED</span></div><div className="synthesis-preview">{synthesis}</div><div className="agent-grid">{(result.contributions || []).map((item: any) => <div className="agent-card" key={item.provider}><strong>{item.role.replaceAll("_", " ")}</strong><span>{item.provider} · {item.model}</span><small>{item.sources?.length || 0} grounded sources captured</small></div>)}</div>{(result.warnings || []).length > 0 && <div className="warning-list">{result.warnings.map((warning: string, index: number) => <div key={index}><ShieldCheck size={13} />{warning}</div>)}</div>}<div className="source-list">{(result.contributions || []).flatMap((item: any) => (item.sources || []).map((source: any) => ({...source, agent: item.role}))).map((source: any, index: number) => <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noreferrer"><span>{source.title}</span><small>{source.agent.replaceAll("_", " ")}</small></a>)}</div></div>}
            {selected.status === "needs_review" && synthesis && <div className="stage-block"><div className="subheading"><span>VOICE PRODUCTION</span><span className="review-tag">HUMAN APPROVAL</span></div><label>APPROVED NARRATION SCRIPT</label><textarea className="script-area" rows={8} value={script} onChange={(e) => setScript(e.target.value)} placeholder={result.script_draft ? "Review, edit and approve the AI-generated narration draft..." : "No AI script draft was returned. Write or paste an approved narration script here..."} /><div className="script-metrics"><span>{scriptWordCount.toLocaleString()} WORDS</span><span>EST. {estimatedScriptMinutes.toFixed(1)} MIN AT 135 WPM</span><span>{selected.brief.target_minutes} MIN TARGET</span></div>{scriptReview && <details className="script-audit"><summary><ShieldCheck size={14} /> INDEPENDENT SCRIPT AUDIT</summary><div>{scriptReview}</div></details>}<button className="secondary-button" disabled={!!busy || script.trim().length < 20} onClick={generateNarration}>{busy === "narration" ? <LoaderCircle className="spin" size={16} /> : <Mic2 size={16} />} Generate narration and captions <ArrowRight size={15} /></button></div>}
            {narration && <div className="stage-block"><div className="subheading"><span>FOOTAGE LIBRARY</span><span className="review-tag">{assets.length} CLIPS SELECTED</span></div>{result.storyboard?.beats?.length > 0 && <div className="storyboard-list"><div className="storyboard-heading"><div><span>AI VISUAL STORYBOARD</span><small>{result.storyboard.beats.length} TIMED BEATS · {result.storyboard.fps} FPS</small></div><button disabled={!!busy} onClick={recommendAllFootage}>{busy === "recommend" ? <LoaderCircle className="spin" size={13} /> : <WandSparkles size={13} />} Find footage for all beats</button></div>{result.storyboard.beats.map((beat: any) => <div className={activeBeatId === beat.id ? "storyboard-beat active" : "storyboard-beat"} key={beat.id}><div className="beat-time">{frameTime(beat.start_frame, result.storyboard.fps)}–{frameTime(beat.end_frame, result.storyboard.fps)}</div><div className="beat-copy"><strong>{beat.visual_description}</strong><span>{beat.narration_excerpt}</span><small>{beat.shot_type.toUpperCase()} · {beat.visual_query}</small></div><button disabled={!!busy} onClick={() => searchFootage(beat.visual_query, beat.id)}>{assets.some((asset) => asset.beat_id === beat.id) ? <Check size={14} /> : <Search size={14} />}{assets.some((asset) => asset.beat_id === beat.id) ? "Replace" : "Find footage"}</button>{(beatRecommendations[beat.id] || []).map((candidate) => <div className="beat-recommendation" key={candidate.provider_id}><div><strong>{candidate.creator} · {candidate.width}×{candidate.height}</strong><small>TECHNICAL FIT {candidate.quality_score}/100 · {candidate.duration_seconds}s</small></div><button disabled={!!busy || assets.some((asset) => asset.provider_id === candidate.provider_id)} onClick={() => addAsset(candidate, beat.id)}>{busy === "asset-" + candidate.provider_id ? <LoaderCircle className="spin" size={13} /> : <Plus size={13} />} Add</button></div>)}</div>)}</div>}{result.storyboard_warning && <div className="warning-list"><div><ShieldCheck size={13} />{result.storyboard_warning}</div></div>}<div className="asset-search"><div className="search-input"><Search size={16} /><input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchFootage(searchQuery, activeBeatId)} placeholder={activeBeatId ? "Refine footage search for selected storyboard beat..." : "Select a storyboard beat, or search general footage..."} /></div><button className="secondary-button compact" disabled={!!busy} onClick={() => searchFootage(searchQuery, activeBeatId)}>{busy === "search" ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />} Search Pexels</button></div>{candidates.length > 0 && <div className="candidate-list">{candidates.map((candidate) => <div className="candidate" key={candidate.provider_id}><div><strong>{candidate.title}</strong><span>{candidate.creator} · {candidate.width}×{candidate.height} · {candidate.duration_seconds}s</span><small className="candidate-fit">TECHNICAL FIT {candidate.quality_score}/100 · {candidate.quality_notes.join(" · ")}</small></div><button disabled={!!busy || assets.some((asset) => asset.provider_id === candidate.provider_id)} onClick={() => addAsset(candidate)}>{busy === `asset-${candidate.provider_id}` ? <LoaderCircle className="spin" size={14} /> : <Plus size={14} />} Add clip</button></div>)}</div>}{assets.length > 0 && <div className="selected-assets">{assets.map((asset) => <div key={asset.provider_id}><Film size={15} /><span>{asset.title}</span><small>{asset.beat_id ? "Storyboard beat" : asset.creator}</small><Check size={14} /></div>)}</div>}<div className="render-action"><div><strong>Ready to assemble</strong><span>{storyboard?.beats?.length ? `${coveredBeats}/${storyboard.beats.length} storyboard beats covered` : "1920×1080 · 30fps · source metadata retained"}</span></div><button className="primary-button" disabled={!!busy || !assets.length || (storyboard?.beats?.length > 0 && coveredBeats !== storyboard.beats.length)} onClick={renderVideo}>{busy === "render" ? <LoaderCircle className="spin" size={16} /> : <Clapperboard size={16} />} Render documentary <ArrowRight size={15} /></button></div></div>}
            {selected.status === "completed" && <div className="completed-block"><div className="completed-mark"><Check size={22} /></div><div><strong>Documentary rendered and validated</strong><span>{result.render?.duration_seconds?.toFixed(1)} seconds · {result.render?.width}×{result.render?.height} · {(result.render?.size_bytes / 1024 / 1024).toFixed(1)} MB</span></div><a className="download-button" href={`${API}/api/jobs/${selected.id}/video`}><ArrowDownToLine size={16} /> Download MP4</a></div>}
            <div className="event-log"><div className="subheading"><span>JOB EVENT LOG</span><span>{selected.events.length} EVENTS</span></div>{selected.events.slice().reverse().slice(0, 6).map((event, index) => <div className="event-row" key={`${event.type}-${index}`}><span className="event-dot" /><code>{event.type}</code><time>{dateLabel(event.created_at)}</time></div>)}</div>
          </section>}
          <footer className="footer"><span>JACK POCKETS PRO MAX</span><span>RESEARCH FIRST. EDIT WITH INTENT. VERIFY EVERY FRAME.</span><span>0.2.0</span></footer>
        </div>
      </main>
    </div>
  );
}
