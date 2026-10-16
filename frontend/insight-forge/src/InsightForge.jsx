import React, { useState, useRef, useEffect } from "react";

const iconProps = (size, className) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", className,
});
const Plus = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M12 5v14M5 12h14" /></svg>;
const FileText = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M9 13h6M9 17h6" /></svg>;
const X = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M18 6 6 18M6 6l12 12" /></svg>;
const Send = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>;
const User = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M20 21a8 8 0 0 0-16 0" /><circle cx="12" cy="7" r="4" /></svg>;
const ChevronDown = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="m6 9 6 6 6-6" /></svg>;
const ChevronLeft = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="m15 18-6-6 6-6" /></svg>;
const UploadCloud = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M4 14.9A5 5 0 0 1 6 5.3a6 6 0 0 1 11.6 1.7A4.5 4.5 0 0 1 18 16H7a3 3 0 0 1-3-1.1Z" /><path d="M12 12v7M9 16l3-3 3 3" /></svg>;
const MessageSquare = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>;
const Sparkles = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6Z" /></svg>;
const AlertCircle = ({ size = 16, className }) => <svg {...iconProps(size, className)}><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>;
const Check = ({ size = 16, className }) => <svg {...iconProps(size, className)}><path d="M20 6 9 17l-5-5" /></svg>;

const c = {
  bg: "#0D1117", panel: "#151B23", panelAlt: "#1C242E", border: "#2A323C",
  borderSoft: "#212830", text: "#E6EDF3", textMuted: "#8B949E", textFaint: "#5B6472",
  accent: "#5B8DEF", accentSoft: "#182545", accentText: "#B9D1FF",
  userBubble: "#1C2638", errorBg: "#2A1A1A", errorBorder: "#5C2626", errorText: "#F87171",
};
const MAX_DOCUMENTS = 5;
const COLLECTION = "Docs";

function uid() { return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`; }

function renderInline(str) {
  return str.split(/(\*\*.+?\*\*)/g).map((s, j) =>
    s.startsWith("**") && s.endsWith("**")
      ? <strong key={j} style={{ fontWeight: 600, color: c.text }}>{s.slice(2, -2)}</strong>
      : s
  );
}

function RichText({ text }) {
  const lines = text.split("\n");
  const base = { margin: 0, textAlign: "left" };
  return (
    <div style={{ lineHeight: 1.7, textAlign: "left" }}>
      {lines.map((line, i) => {
        if (/^### /.test(line)) return <p key={i} style={{ ...base, fontWeight: 700, fontSize: 13, color: c.accentText, marginTop: 10 }}>{renderInline(line.slice(4))}</p>;
        if (/^## /.test(line)) return <p key={i} style={{ ...base, fontWeight: 700, fontSize: 14, color: c.accentText, marginTop: 12 }}>{renderInline(line.slice(3))}</p>;
        if (/^# /.test(line)) return <p key={i} style={{ ...base, fontWeight: 700, fontSize: 15, color: c.accentText, marginTop: 14 }}>{renderInline(line.slice(2))}</p>;

        const bullet = line.match(/^\s*[*\-•] (.*)/);
        if (bullet) return (
          <div key={i} style={{ display: "flex", gap: 8, marginTop: 4, paddingLeft: 4, textAlign: "left" }}>
            <span style={{ color: c.accent, flexShrink: 0 }}>•</span>
            <span style={{ flex: 1 }}>{renderInline(bullet[1])}</span>
          </div>
        );

        const num = line.match(/^\s*(\d+)\. (.*)/);
        if (num) return (
          <div key={i} style={{ display: "flex", gap: 8, marginTop: 4, paddingLeft: 4, textAlign: "left" }}>
            <span style={{ color: c.accent, flexShrink: 0, minWidth: 18 }}>{num[1]}.</span>
            <span style={{ flex: 1 }}>{renderInline(num[2])}</span>
          </div>
        );

        if (!line.trim()) return <div key={i} style={{ height: 8 }} />;
        return <p key={i} style={{ ...base, marginTop: 2 }}>{renderInline(line)}</p>;
      })}
    </div>
  );
}

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "4px 0" }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: "50%", backgroundColor: c.accent,
          animation: `_bounce 1.2s ease-in-out ${i * 0.2}s infinite`
        }} />
      ))}
      <style>{`@keyframes _bounce{0%,80%,100%{transform:translateY(0);opacity:.4}40%{transform:translateY(-6px);opacity:1}}`}</style>
    </div>
  );
}

function SectionLabel({ children }) {
  return <p style={{ color: c.textFaint, fontSize: 11, fontWeight: 500, padding: "20px 16px 8px", margin: 0 }}>{children}</p>;
}

function DocumentRow({ doc, onRemove }) {
  const [hover, setHover] = useState(false);
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 12px 6px", padding: "8px 10px", borderRadius: 6, backgroundColor: c.panelAlt }}>
      <FileText size={15} style={{ color: c.accent, flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: c.text, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={doc.name}>{doc.name}</span>
      <button onClick={() => onRemove(doc.id)} aria-label={`Remove ${doc.name}`}
        style={{ color: c.textMuted, background: "none", border: "none", cursor: "pointer", padding: 2, borderRadius: 4, flexShrink: 0, opacity: hover ? 1 : 0, transition: "opacity 150ms" }}>
        <X size={14} />
      </button>
    </div>
  );
}

function ChatRow({ chat, onSelect }) {
  return (
    <button onClick={() => onSelect(chat.id)}
      style={{
        width: "calc(100% - 24px)", display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", margin: "0 12px 4px",
        borderRadius: 6, backgroundColor: chat.active ? c.panelAlt : "transparent", border: "none", cursor: "pointer", textAlign: "left"
      }}>
      <MessageSquare size={14} style={{ color: chat.active ? c.accent : c.textFaint, flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: chat.active ? c.text : c.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{chat.title}</span>
    </button>
  );
}

function ContextPicker({ message, onSelect, onCancel }) {
  const [hovered, setHovered] = useState(null);
  const { contexts, selected, cancelled } = message;
  const resolved = selected != null || cancelled;

  return (
    <div style={{ display: "flex", marginBottom: 20 }}>
      <div style={{
        flexShrink: 0, marginRight: 12, marginTop: 2, width: 28, height: 28, borderRadius: "50%",
        backgroundColor: c.accentSoft, display: "flex", alignItems: "center", justifyContent: "center"
      }}>
        <Sparkles size={13} style={{ color: c.accent }} />
      </div>

      <div style={{ width: "100%", maxWidth: "72%", fontSize: 13, color: c.text }}>
        <p style={{ margin: "6px 0 4px", lineHeight: 1.6, textAlign: "left" }}>
          {cancelled
            ? "Context selection skipped."
            : selected != null
              ? <>Using context: <strong style={{ fontWeight: 600 }}>{contexts[selected].label}</strong></>
              : "Your documents cover this topic in more than one context. Which one do you mean?"}
        </p>

        {!cancelled && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
            {contexts.map((ctx, i) => {
              const isSel = selected === i;
              const isHover = hovered === i && !resolved;
              return (
                <button key={i} disabled={resolved} onClick={() => onSelect(message.id, i)}
                  onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}
                  aria-label={`Select context ${ctx.label}`}
                  style={{
                    display: "flex", gap: 12, alignItems: "flex-start", textAlign: "left", width: "100%",
                    padding: "10px 12px", borderRadius: 10, fontFamily: "inherit",
                    backgroundColor: isSel ? c.accentSoft : isHover ? c.panelAlt : c.panel,
                    border: `1px solid ${isSel || isHover ? c.accent : c.border}`,
                    opacity: resolved && !isSel ? 0.45 : 1,
                    cursor: resolved ? "default" : "pointer", transition: "all 150ms", color: c.text
                  }}>
                  <span style={{
                    flexShrink: 0, width: 22, height: 22, borderRadius: "50%", fontSize: 11, fontWeight: 600,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    backgroundColor: isSel ? c.accent : c.panelAlt, color: isSel ? c.bg : c.textMuted
                  }}>
                    {isSel ? <Check size={12} /> : i + 1}
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: "block", fontWeight: 600, fontSize: 13, color: c.text }}>{ctx.label}</span>
                    {ctx.description && (
                      <span style={{ display: "block", marginTop: 2, lineHeight: 1.5, color: c.textMuted }}>{ctx.description}</span>
                    )}
                    {Array.isArray(ctx.sources) && ctx.sources.length > 0 && (
                      <span style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        {ctx.sources.map(src => (
                          <span key={src} title={src} style={{
                            maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            fontSize: 11, padding: "2px 8px", borderRadius: 999,
                            backgroundColor: c.panelAlt, color: c.textMuted, border: `1px solid ${c.borderSoft}`
                          }}>{src}</span>
                        ))}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {!resolved && (
          <button onClick={() => onCancel(message.id)}
            style={{
              marginTop: 10, padding: 0, background: "none", border: "none", cursor: "pointer",
              fontSize: 12, color: c.textFaint, fontFamily: "inherit", textDecoration: "underline"
            }}>
            Skip &amp; ask something else
          </button>
        )}
      </div>
    </div>
  );
}

function MessageBubble({ message, onSelectContext, onCancelContext }) {
  if (message.role === "clarify") {
    return <ContextPicker message={message} onSelect={onSelectContext} onCancel={onCancelContext} />;
  }
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const isLoading = message.role === "loading";
  const bubbleBg = isUser ? c.userBubble : isError ? c.errorBg : "transparent";
  const border = isUser ? `1px solid ${c.border}` : isError ? `1px solid ${c.errorBorder}` : "none";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 20 }}>
      {!isUser && (
        <div style={{
          flexShrink: 0, marginRight: 12, marginTop: 2, width: 28, height: 28, borderRadius: "50%",
          backgroundColor: isError ? c.errorBg : c.accentSoft, display: "flex", alignItems: "center", justifyContent: "center"
        }}>
          {isError ? <AlertCircle size={14} style={{ color: c.errorText }} /> : <Sparkles size={13} style={{ color: c.accent }} />}
        </div>
      )}
      <div style={{ maxWidth: "72%", padding: "12px 16px", borderRadius: 12, backgroundColor: bubbleBg, border, fontSize: 13, color: isError ? c.errorText : c.text }}>
        {isLoading ? <TypingDots /> : isUser ? <p style={{ lineHeight: 1.6, margin: 0, whiteSpace: "pre-wrap" }}>{message.text}</p>
          : isError ? <p style={{ lineHeight: 1.6, margin: 0 }}>{message.text}</p>
            : <RichText text={message.text} />}
      </div>
      {isUser && (
        <div style={{
          flexShrink: 0, marginLeft: 12, marginTop: 2, width: 28, height: 28, borderRadius: "50%",
          backgroundColor: c.panelAlt, display: "flex", alignItems: "center", justifyContent: "center"
        }}>
          <User size={13} style={{ color: c.textMuted }} />
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, paddingTop: 80 }}>
      <div style={{ width: 56, height: 56, borderRadius: 16, backgroundColor: c.accentSoft, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Sparkles size={26} style={{ color: c.accent }} />
      </div>
      <p style={{ fontSize: 15, fontWeight: 600, color: c.text, margin: 0 }}>Ask anything about your documents</p>
      <p style={{ fontSize: 13, color: c.textMuted, margin: 0, textAlign: "center", maxWidth: 300, lineHeight: 1.6 }}>
        Upload a PDF or document on the left, then type your question below.
        InsightForge searches your knowledge base and returns a grounded answer.
      </p>
    </div>
  );
}

export default function InsightForge() {
  const [documents, setDocuments] = useState([]);
  const [chats, setChats] = useState([]);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);

  const fileInputRef = useRef(null);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const atLimit = documents.length >= MAX_DOCUMENTS;

  useEffect(() => { fetchDocuments(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => {
    const ta = textareaRef.current; if (!ta) return;
    ta.style.height = "auto"; ta.style.height = `${Math.min(ta.scrollHeight, 128)}px`;
  }, [draft]);

  const fetchDocuments = async () => {
    try {
      const res = await fetch("/api/documents/");
      if (res.ok) { const d = await res.json(); setDocuments(d.map(x => ({ id: x.id, name: x.original_name }))); }
    } catch (e) { console.error(e); }
  };

  const handleUploadClick = () => { if (!atLimit && !uploading) fileInputRef.current?.click(); };

  const handleFilesSelected = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    if (documents.length + files.length > MAX_DOCUMENTS) alert(`Max ${MAX_DOCUMENTS} docs. Extra files skipped.`);
    const toUpload = files.slice(0, MAX_DOCUMENTS - documents.length);
    setUploading(true);
    for (const file of toUpload) {
      const fd = new FormData(); fd.append("file", file);
      try {
        const res = await fetch("/api/documents/", { method: "POST", body: fd });
        if (res.ok) { const doc = await res.json(); setDocuments(p => [...p, { id: doc.id, name: doc.original_name }]); }
        else { const err = await res.json(); alert(`Failed: ${err.error || "Unknown"}`); }
      } catch (e) { alert(`Error uploading ${file.name}`); }
    }
    setUploading(false); e.target.value = "";
  };

  const removeDocument = async (id) => {
    const res = await fetch(`/api/documents/${id}/`, { method: "DELETE" });
    if (res.ok || res.status === 204) setDocuments(p => p.filter(d => d.id !== id));
  };

  const selectChat = (id) => setChats(p => p.map(x => ({ ...x, active: x.id === id })));
  const startNewChat = () => {
    const id = uid();
    setChats(p => [{ id, title: "New chat", active: true }, ...p.map(x => ({ ...x, active: false }))]);
    setMessages([]);
  };

  // A clarification card is waiting for the user's choice
  const pendingClarify = messages.some(m => m.role === "clarify" && m.selected == null && !m.cancelled);
  const busy = isQuerying || pendingClarify;

  const replaceLoading = (loadId, msg) =>
    setMessages(p => [...p.filter(m => m.id !== loadId), { id: uid(), ...msg }]);

  // Single entry point to /api/search/. The backend answers with either
  //   { answer }                                                   -> normal reply
  //   { needs_clarification: true, thread_id, contexts: [...] }    -> ask the user to pick a context
  // and a follow-up call with { thread_id, selection } resumes the agent.
  const requestAnswer = async (body, loadId) => {
    try {
      const res = await fetch("/api/search/", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data[Object.keys(data)[0]] || `Server error (${res.status})`;
        replaceLoading(loadId, { role: "error", text: msg });
      } else if (data.needs_clarification && Array.isArray(data.contexts) && data.contexts.length > 1) {
        replaceLoading(loadId, {
          role: "clarify", text: "", threadId: data.thread_id,
          contexts: data.contexts, selected: null, cancelled: false,
        });
      } else {
        replaceLoading(loadId, { role: "assistant", text: data.answer || "(empty)" });
      }
    } catch (e) {
      replaceLoading(loadId, { role: "error", text: `Network error: ${e.message}` });
    } finally { setIsQuerying(false); }
  };

  const handleSelectContext = async (msgId, idx) => {
    const m = messages.find(x => x.id === msgId);
    if (!m || m.selected != null || m.cancelled || isQuerying) return;
    const loadId = uid();
    setMessages(p => [
      ...p.map(x => x.id === msgId ? { ...x, selected: idx } : x),
      { id: uid(), role: "user", text: `Use context: ${m.contexts[idx].label}` },
      { id: loadId, role: "loading", text: "" },
    ]);
    setIsQuerying(true);
    await requestAnswer({ collection: COLLECTION, thread_id: m.threadId, selection: idx + 1 }, loadId);
  };

  const handleCancelContext = (msgId) =>
    setMessages(p => p.map(x => x.id === msgId ? { ...x, cancelled: true } : x));

  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    const loadId = uid();
    setMessages(p => [...p, { id: uid(), role: "user", text }, { id: loadId, role: "loading", text: "" }]);
    setDraft(""); setIsQuerying(true);
    const title = text.length > 42 ? text.slice(0, 42) + "…" : text;
    setChats(p => {
      const a = p.find(x => x.active);
      if (a && a.title === "New chat") return p.map(x => x.id === a.id ? { ...x, title } : x);
      if (!a) return [{ id: uid(), title, active: true }, ...p.map(x => ({ ...x, active: false }))];
      return p;
    });
    await requestAnswer({ query: text, collection: COLLECTION }, loadId);
  };

  const handleKeyDown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };

  return (
    <div style={{ position: "fixed", inset: 0, display: "flex", overflow: "hidden", backgroundColor: c.bg, fontFamily: "system-ui,-apple-system,sans-serif" }}>

      {/* ── Sidebar ── */}
      <aside style={{
        width: collapsed ? 68 : 272, flexShrink: 0, display: "flex", flexDirection: "column",
        borderRight: `1px solid ${c.border}`, backgroundColor: c.panel, transition: "width 200ms", position: "relative", overflow: "hidden"
      }}>

        <button onClick={() => setCollapsed(v => !v)} aria-label={collapsed ? "Expand" : "Collapse"}
          style={{
            position: "absolute", right: -12, top: 24, width: 24, height: 24, borderRadius: "50%",
            backgroundColor: c.panelAlt, border: `1px solid ${c.border}`, color: c.textMuted,
            display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", zIndex: 10
          }}>
          <ChevronLeft size={13} style={{ transform: collapsed ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
        </button>

        <div style={{ padding: collapsed ? "16px 8px 0" : "16px 12px 0" }}>
          <button id="btn-new-chat" onClick={startNewChat} aria-label="New chat"
            style={{
              width: "100%", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start",
              gap: 8, padding: collapsed ? "10px" : "10px 12px", borderRadius: 6,
              backgroundColor: c.accentSoft, color: c.accentText, border: `1px solid ${c.accent}33`,
              fontSize: 13, fontWeight: 500, cursor: "pointer"
            }}>
            <Plus size={16} />{!collapsed && "New chat"}
          </button>
        </div>

        {collapsed ? (
          <button onClick={() => setCollapsed(false)} style={{
            position: "relative", margin: "20px 8px 0", padding: "10px 0",
            display: "flex", alignItems: "center", justifyContent: "center", color: c.textMuted, background: "none", border: "none", cursor: "pointer", borderRadius: 6
          }}>
            <FileText size={17} />
            <span style={{ position: "absolute", top: 4, right: 6, fontSize: 10, backgroundColor: c.accentSoft, color: c.accentText, borderRadius: 999, padding: "1px 4px" }}>{documents.length}</span>
          </button>
        ) : (<>
          <SectionLabel>Documents</SectionLabel>
          <div style={{ flexShrink: 0 }}>
            {documents.map(doc => <DocumentRow key={doc.id} doc={doc} onRemove={removeDocument} />)}
            <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.txt,.md" style={{ display: "none" }} onChange={handleFilesSelected} />
            <button id="btn-upload-document" onClick={handleUploadClick} disabled={atLimit || uploading}
              style={{
                width: "calc(100% - 24px)", display: "flex", alignItems: "center", gap: 10, margin: "0 12px 4px",
                padding: "8px 10px", borderRadius: 6, border: `1px dashed ${atLimit || uploading ? c.borderSoft : c.border}`,
                backgroundColor: "transparent", color: atLimit || uploading ? c.textFaint : c.textMuted,
                fontSize: 13, cursor: atLimit || uploading ? "not-allowed" : "pointer"
              }}>
              <UploadCloud size={15} style={{ flexShrink: 0 }} />
              {uploading ? "Uploading…" : atLimit ? "Upload limit reached" : "Upload document"}
            </button>
            <p style={{ fontSize: 11, color: c.textFaint, padding: "2px 16px 4px", margin: 0 }}>{documents.length} of {MAX_DOCUMENTS} uploaded</p>
          </div>
        </>)}

        {collapsed ? (
          <button onClick={() => setCollapsed(false)} style={{
            margin: "20px 8px 0", padding: "10px 0",
            display: "flex", alignItems: "center", justifyContent: "center", color: c.textMuted, background: "none", border: "none", cursor: "pointer", borderRadius: 6
          }}>
            <MessageSquare size={17} />
          </button>
        ) : (<>
          {chats.length > 0 && <SectionLabel>Previous chats</SectionLabel>}
          <div style={{ flex: 1, overflowY: "auto", paddingBottom: 12 }}>
            {chats.map(chat => <ChatRow key={chat.id} chat={chat} onSelect={selectChat} />)}
          </div>
        </>)}
      </aside>

      {/* ── Main column ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>

        <header style={{
          position: "relative", display: "flex", alignItems: "center", justifyContent: "center",
          height: 56, flexShrink: 0, borderBottom: `1px solid ${c.border}`, backgroundColor: c.bg, padding: "0 24px"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: c.accentSoft, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Sparkles size={13} style={{ color: c.accent }} />
            </div>
            <h1 style={{ fontSize: 15, fontWeight: 600, color: c.text, margin: 0, letterSpacing: -0.3 }}>InsightForge</h1>
          </div>
          <button id="btn-user-menu" style={{
            position: "absolute", right: 24, display: "flex", alignItems: "center",
            gap: 8, padding: "4px 8px 4px 4px", borderRadius: 999, backgroundColor: c.panel, border: "none", cursor: "pointer"
          }}>
            <span style={{ width: 28, height: 28, borderRadius: "50%", backgroundColor: c.accentSoft, color: c.accent, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <User size={14} />
            </span>
            <span style={{ fontSize: 13, color: c.text }}>Usman</span>
            <ChevronDown size={14} style={{ color: c.textMuted }} />
          </button>
        </header>

        <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
          <div style={{ maxWidth: 672, margin: "0 auto" }}>
            {messages.length === 0 ? <EmptyState /> : messages.map(m => <MessageBubble key={m.id} message={m} onSelectContext={handleSelectContext} onCancelContext={handleCancelContext} />)}
            <div ref={bottomRef} />
          </div>
        </div>

        <div style={{ flexShrink: 0, padding: "8px 24px 24px", backgroundColor: c.bg }}>
          <div style={{
            maxWidth: 672, margin: "0 auto", borderRadius: 12,
            border: `1px solid ${isQuerying ? c.accent : c.border}`, backgroundColor: c.panel, transition: "border-color 200ms"
          }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, padding: "8px 12px" }}>
              <textarea id="chat-input" ref={textareaRef} value={draft} rows={1} disabled={busy}
                onChange={e => setDraft(e.target.value)} onKeyDown={handleKeyDown}
                placeholder={isQuerying ? "Thinking…" : pendingClarify ? "Choose a context above to continue…" : "Ask anything about your documents…"}
                style={{
                  flex: 1, background: "transparent", border: "none", outline: "none", resize: "none",
                  fontSize: 13, color: c.text, padding: "6px 0", maxHeight: 128, fontFamily: "inherit"
                }} />
              <button id="btn-send" onClick={sendMessage} disabled={!draft.trim() || busy} aria-label="Send"
                style={{
                  flexShrink: 0, width: 32, height: 32, borderRadius: 8, border: "none",
                  backgroundColor: draft.trim() && !busy ? c.accent : c.panelAlt,
                  color: draft.trim() && !busy ? c.bg : c.textFaint,
                  cursor: draft.trim() && !busy ? "pointer" : "default",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transform: draft.trim() && !busy ? "scale(1.05)" : "scale(1)", transition: "all 150ms"
                }}>
                <Send size={15} />
              </button>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0 12px 8px", fontSize: 11, color: c.textFaint }}>
              <span>{isQuerying ? "Searching knowledge base…" : pendingClarify ? "Waiting for you to pick a context…" : documents.length === 0 ? "No documents uploaded yet" : `${documents.length} doc${documents.length > 1 ? "s" : ""} loaded \u00b7 ${COLLECTION}`}</span>
              <span>Enter to send &middot; Shift+Enter new line</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}