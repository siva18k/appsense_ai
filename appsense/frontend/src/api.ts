export type Project = {
  id: string;
  name: string;
  description: string;
  created_at: string;
};

export type Conversation = {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  extra_json?: string | null;
  created_at: string;
};

export type KbDoc = {
  id: string;
  project_id: string;
  title: string;
  source_type: string;
  filename?: string | null;
  excerpt?: string;
  summary?: string;
  body?: string;
  created_at: string;
  updated_at?: string | null;
};

export type Repo = {
  id: string;
  name: string;
  kind: string;
  source: string;
  local_path: string;
  last_indexed_at?: string | null;
  last_scanned_at?: string | null;
  scan_doc_id?: string | null;
};

export type AllowCommand = {
  id: string;
  name: string;
  description: string;
  cwd: string;
  command: string;
};

export type LogPath = {
  id: string;
  label: string;
  path: string;
};

export type Settings = {
  llm_base_url: string;
  llm_model: string;
  embedding_model: string;
  chroma_path: string;
  sqlite_path: string;
  has_api_key: boolean;
  env_path: string;
  default_command_cwd: string;
  default_command_python: string;
  target_app_root: string;
  target_app_python: string;
  target_app_env_file: string;
};

export type CommandProposal = {
  id: string;
  name: string;
  description: string;
  command: string;
  cwd: string;
  reason?: string;
  draft?: boolean;
};

export type Skill = {
  id: string;
  project_id: string;
  name: string;
  goal: string;
  body: string;
  refined: boolean;
  summary?: string;
  created_at: string;
  updated_at: string;
  compiled: boolean;
  tested: boolean;
  test_output?: string;
  tested_at?: string | null;
};

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return res.statusText;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function readSse(
  res: Response,
  onEvent: (data: Record<string, unknown>) => void
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        /* ignore partial json */
      }
    }
  }
  if (buf.trim()) {
    const line = buf.split("\n").find((l) => l.startsWith("data:"));
    if (line) {
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        /* ignore incomplete final json */
      }
    }
  }
}
