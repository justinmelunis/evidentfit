"use client";

import { useRef, useState, useEffect } from "react";
import LoginModal from "@/components/LoginModal";

type Msg = { role: "user" | "assistant"; content: string };
type Hit = { title: string; url_pub: string; study_type: string; doi: string; pmid: string };

export default function Agent() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [showLogin, setShowLogin] = useState(false);
  const [authError, setAuthError] = useState("");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const tid = useRef<string>(crypto.randomUUID());

  // Check for stored credentials on mount
  useEffect(() => {
    const storedUsername = sessionStorage.getItem("chat_username");
    const storedPassword = sessionStorage.getItem("chat_password");
    if (storedUsername && storedPassword) {
      setIsAuthenticated(true);
    } else {
      setShowLogin(true);
    }
  }, []);

  const handleLogin = (username: string, password: string) => {
    // Store credentials in sessionStorage (cleared on browser close)
    sessionStorage.setItem("chat_username", username);
    sessionStorage.setItem("chat_password", password);
    setIsAuthenticated(true);
    setShowLogin(false);
    setAuthError("");
  };

  const handleLogout = () => {
    sessionStorage.removeItem("chat_username");
    sessionStorage.removeItem("chat_password");
    setIsAuthenticated(false);
    setMsgs([]);
    setHits([]);
    setShowLogin(true);
  };

  const testConnection = async () => {
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const testUrl = `${apiBase}/test-frontend`;
      console.log("Testing connection to:", testUrl);
      const res = await fetch(testUrl);
      const text = await res.text();
      const data = JSON.parse(text);
      alert("Connection test: " + JSON.stringify(data));
    } catch (error) {
      console.error("Connection test failed:", error);
      alert("Connection test failed: " + (error instanceof Error ? error.message : String(error)));
    }
  };

  const send = async () => {
    if (!isAuthenticated) {
      setShowLogin(true);
      return;
    }

    const newMsgs = [...msgs, { role: "user" as const, content: input }];
    setMsgs(newMsgs);
    setInput("");
    setLoading(true);
    setHits([]);

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const username = sessionStorage.getItem("chat_username") || "demo";
      const password = sessionStorage.getItem("chat_password") || "demo123";

      const apiUrl = `${apiBase}/stream`;
      const authString = btoa(`${username}:${password}`);

      const profile = {
        goal: "strength",
        weight_kg: 80,
        caffeine_sensitive: false,
        meds: [],
      };

      const res = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          Authorization: "Basic " + authString,
        },
        body: JSON.stringify({
          thread_id: tid.current,
          messages: newMsgs,
          profile: profile,
        }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          setAuthError("Invalid username or password");
          setIsAuthenticated(false);
          setShowLogin(true);
          setLoading(false);
          return;
        }
        const errorData = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errorData.detail || `HTTP error! status: ${res.status}`);
      }

      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let acc = "";
      let finalAnswer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = dec.decode(value);
        acc += chunk;

        const lines = acc.split("\n");
        acc = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const jsonStr = line.slice(5).trim();
            const ev = JSON.parse(jsonStr);

            if (ev.stage === "search" && ev.hits) {
              setHits(ev.hits);
            }

            if (ev.stage === "final" && ev.answer) {
              finalAnswer = ev.answer;
            }
          } catch (e) {
            console.error("Error parsing SSE event:", e);
          }
        }
      }

      if (finalAnswer) {
        setMsgs([...newMsgs, { role: "assistant", content: finalAnswer }]);
      } else {
        setMsgs([
          ...newMsgs,
          { role: "assistant", content: "Sorry, I couldn't process your request. Please try again." },
        ]);
      }
    } catch (error) {
      console.error("Error sending message:", error);
      setMsgs([
        ...newMsgs,
        { role: "assistant" as const, content: "Error: " + (error instanceof Error ? error.message : String(error)) },
      ]);
    }

    setLoading(false);
  };

  if (!isAuthenticated && !showLogin) {
    return null; // Wait for auth check
  }

  return (
    <>
      <LoginModal
        isOpen={showLogin}
        onClose={() => {
          setShowLogin(false);
          setAuthError("");
        }}
        onLogin={handleLogin}
        error={authError}
      />
      <main className="max-w-3xl mx-auto p-8">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-semibold">Research Chat</h1>
          {isAuthenticated && (
            <button
              onClick={handleLogout}
              className="text-sm text-gray-600 hover:text-gray-800 px-3 py-1 border border-gray-300 rounded"
            >
              Logout
            </button>
          )}
        </div>

        {hits.length > 0 && (
          <div className="mb-4 p-3 bg-blue-50 rounded">
            <h3 className="text-sm font-medium mb-2">Found {hits.length} relevant studies:</h3>
            <div className="space-y-1">
              {hits.map((hit, i) => (
                <div key={i} className="text-xs">
                  <span className="font-medium">{hit.title}</span>
                  {hit.study_type && <span className="text-gray-600"> ({hit.study_type})</span>}
                  {hit.doi && <span className="text-blue-600"> DOI: {hit.doi}</span>}
                  {hit.pmid && <span className="text-green-600"> PMID: {hit.pmid}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="border rounded p-4 space-y-3 min-h-[200px]">
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
              <span
                className={
                  (m.role === "user" ? "bg-blue-100" : "bg-gray-100") + " px-3 py-2 rounded inline-block"
                }
              >
                {m.content}
              </span>
            </div>
          ))}
          {loading && <div className="text-sm text-gray-500">Searching and analyzing…</div>}
        </div>

        <div className="mt-4 flex gap-2">
          <input
            className="border rounded px-3 py-2 flex-1"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && !loading && input && send()}
            placeholder="Ask about creatine, caffeine, beta-alanine…"
            disabled={!isAuthenticated}
          />
          <button
            onClick={send}
            disabled={!input || loading || !isAuthenticated}
            className="bg-black text-white px-4 py-2 rounded disabled:opacity-50"
          >
            Send
          </button>
          <button onClick={testConnection} className="bg-gray-500 text-white px-4 py-2 rounded">
            Test Connection
          </button>
        </div>

        <p className="text-xs text-gray-500 mt-3">Educational only; not medical advice.</p>
      </main>
    </>
  );
}
