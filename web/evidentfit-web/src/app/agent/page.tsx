"use client";
import { useRef, useState } from "react";

type Msg = { role: "user"|"assistant"; content: string };
export default function Agent() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const tid = useRef<string>(crypto.randomUUID());

  const testConnection = async () => {
    try {
      // Try hardcoded values first to test if env vars are the issue
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const testUrl = `${apiBase}/test-frontend`;
      console.log("Testing connection to:", testUrl);
      console.log("API Base:", apiBase);
      console.log("Env var NEXT_PUBLIC_API_BASE:", process.env.NEXT_PUBLIC_API_BASE);
      
      const res = await fetch(testUrl);
      console.log("Response status:", res.status);
      console.log("Response headers:", res.headers);
      
      const text = await res.text();
      console.log("Response text:", text);
      
      const data = JSON.parse(text);
      console.log("Connection test result:", data);
      alert("Connection test: " + JSON.stringify(data));
    } catch (error) {
      console.error("Connection test failed:", error);
      alert("Connection test failed: " + (error instanceof Error ? error.message : String(error)));
    }
  };

  const send = async () => {
    const newMsgs = [...msgs, {role:"user" as const, content: input}];
    setMsgs(newMsgs); setInput(""); setLoading(true);

    try {
      // Use hardcoded values since env vars aren't loading
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const demoUser = process.env.NEXT_PUBLIC_DEMO_USER || "demo";
      const demoPw = process.env.NEXT_PUBLIC_DEMO_PW || "demo123";
      
      const apiUrl = `${apiBase}/stream`;
      const authString = btoa(`${demoUser}:${demoPw}`);
      
      console.log("API URL:", apiUrl);
      console.log("Auth string:", authString);
      console.log("Request body:", {thread_id: tid.current, messages: newMsgs});
      
      const res = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "content-type":"application/json",
          "Authorization":"Basic " + authString
        },
        body: JSON.stringify({thread_id: tid.current, messages: newMsgs})
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let acc = "";
      let finalAnswer = "";
      
      console.log("Starting SSE stream reading...");
      
      while(true){
        const {value, done} = await reader.read();
        if (done) {
          console.log("Stream ended, final answer:", finalAnswer);
          break;
        }
        
        const chunk = dec.decode(value);
        acc += chunk;
        console.log("Received chunk:", chunk);
        
        // Process each line that starts with "data:"
        const lines = acc.split('\n');
        acc = lines.pop() || ""; // Keep the last incomplete line
        
        console.log("Processing lines:", lines);
        
        for (const line of lines){
          console.log("Processing line:", line);
          if (!line.startsWith("data:")) continue;
          try{
            const jsonStr = line.slice(5).trim();
            console.log("JSON string:", jsonStr);
            const ev = JSON.parse(jsonStr);
            console.log("Parsed event:", ev);
            
            if (ev.stage === "final" && ev.answer){
              finalAnswer = ev.answer;
              console.log("Found final answer:", finalAnswer);
            }
          }catch(e){
            console.error("Error parsing SSE event:", e, "Raw:", line);
          }
        }
      }
      
      if (finalAnswer) {
        setMsgs([...newMsgs, {role:"assistant", content: finalAnswer}]);
      } else {
        // Fallback: show error message
        setMsgs([...newMsgs, {role:"assistant", content: "Sorry, I couldn't process your request. Please try again."}]);
      }
    } catch (error) {
      console.error("Error sending message:", error);
      setMsgs([...newMsgs, {role:"assistant" as const, content: "Error: " + (error instanceof Error ? error.message : String(error))}]);
    }
    
    setLoading(false);
  };

  return (
    <main className="max-w-3xl mx-auto p-8">
      <h1 className="text-2xl font-semibold mb-4">EvidentFit (private preview)</h1>
      <div className="text-xs text-gray-400 mb-4">
        Debug: API={process.env.NEXT_PUBLIC_API_BASE || "undefined"}, User={process.env.NEXT_PUBLIC_DEMO_USER || "undefined"}
        <br />
        Hardcoded test: http://127.0.0.1:8000
      </div>
      <div className="border rounded p-4 space-y-3 min-h-[200px]">
        {msgs.map((m,i)=>(
          <div key={i} className={m.role==="user"?"text-right":"text-left"}>
            <span className={(m.role==="user"?"bg-blue-100":"bg-gray-100")+" px-3 py-2 rounded inline-block"}>
              {m.content}
            </span>
          </div>
        ))}
        {loading && <div className="text-sm text-gray-500">Thinking…</div>}
      </div>
      <div className="mt-4 flex gap-2">
        <input className="border rounded px-3 py-2 flex-1"
               value={input} onChange={e=>setInput(e.target.value)}
               onKeyPress={e=>e.key==='Enter' && !loading && input && send()}
               placeholder="Ask about creatine, caffeine, beta-alanine…" />
        <button onClick={send} disabled={!input || loading}
                className="bg-black text-white px-4 py-2 rounded disabled:opacity-50">Send</button>
        <button onClick={testConnection}
                className="bg-gray-500 text-white px-4 py-2 rounded">Test Connection</button>
      </div>
      <p className="text-xs text-gray-500 mt-3">Not medical advice. Private preview.</p>
    </main>
  );
}
