import express, {NextFunction, Request, Response} from "express";
import busboy, {FileInfo} from "busboy";

const app = express();
const port = Number(process.env.PORT || 3001);
const telegramBotToken = process.env.TELEGRAM_BOT_TOKEN || "";
const telegramChatId = process.env.TELEGRAM_CHAT_ID || process.env.TELEGRAM_CHANNEL_ID || "";
const frontendOrigin = process.env.FRONTEND_ORIGIN || "*";

app.use((req: Request, res: Response, next: NextFunction) => {
  res.header("Access-Control-Allow-Origin", frontendOrigin === "*" ? "*" : frontendOrigin);
  res.header("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (req.method === "OPTIONS") {
    return res.sendStatus(204);
  }
  next();
});

app.use(express.json({ limit: "100mb" }));

app.get("/", (_req: Request, res: Response) => {
  res.json({
    name: "tg-web-render",
    status: "ok",
    message: "Telegram video forwarding service is running",
    config: {
      telegramBotTokenConfigured: Boolean(telegramBotToken),
      telegramChatIdConfigured: Boolean(telegramChatId),
    },
  });
});

app.get("/health", (_req: Request, res: Response) => {
  res.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    telegramBotTokenConfigured: Boolean(telegramBotToken),
    telegramChatIdConfigured: Boolean(telegramChatId),
  });
});

app.post("/api/telegram/upload-url", async (req: Request, res: Response) => {
  try {
    const { videoUrl, caption = "", parseMode = "HTML" } = req.body || {};

    if (!videoUrl || typeof videoUrl !== "string") {
      return res.status(400).json({ error: "videoUrl is required" });
    }

    if (!telegramBotToken || !telegramChatId) {
      return res.status(500).json({
        error: "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured",
      });
    }

    const result = await sendTelegramVideo({
      video: videoUrl,
      caption,
      parseMode,
    });

    return res.json({ ok: true, result });
  } catch (error) {
    console.error("upload-url failed:", error);
    return res.status(500).json({
      ok: false,
      error: error instanceof Error ? error.message : "unknown_error",
    });
  }
});

app.post("/api/telegram/upload-file", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const parsed = await parseMultipartUpload(req);
    const { file, fields } = parsed;
    const videoUrl = fields.videoUrl || fields.url || "";
    const caption = fields.caption || "";
    const parseMode = fields.parseMode || "HTML";

    if (!telegramBotToken || !telegramChatId) {
      return res.status(500).json({
        error: "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured",
      });
    }

    if (file) {
      const result = await sendTelegramVideo({
        file: {
          buffer: file.buffer,
          filename: file.filename,
          mimeType: file.mimeType,
        },
        caption,
        parseMode,
      });

      return res.json({ ok: true, result, filename: file.filename });
    }

    if (videoUrl) {
      const result = await sendTelegramVideo({
        video: videoUrl,
        caption,
        parseMode,
      });

      return res.json({ ok: true, result });
    }

    return res.status(400).json({ error: "No video file or videoUrl provided" });
  } catch (error) {
    console.error("upload-file failed:", error);
    next(error);
  }
});

app.post("/api/telegram/send-message", async (req: Request, res: Response) => {
  try {
    const { text = "", parseMode = "HTML" } = req.body || {};

    if (!text) {
      return res.status(400).json({ error: "text is required" });
    }

    if (!telegramBotToken || !telegramChatId) {
      return res.status(500).json({
        error: "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured",
      });
    }

    const result = await telegramApiRequest("sendMessage", {
      chat_id: telegramChatId,
      text,
      parse_mode: parseMode,
    });

    return res.json({ ok: true, result });
  } catch (error) {
    console.error("send-message failed:", error);
    return res.status(500).json({
      ok: false,
      error: error instanceof Error ? error.message : "unknown_error",
    });
  }
});

app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  console.error("Unhandled error:", err);
  res.status(500).json({
    ok: false,
    error: err instanceof Error ? err.message : "internal_server_error",
  });
});

const server = app.listen(port, () => {
  console.log(`Telegram video service listening on port ${port}`);
  if (!telegramBotToken || !telegramChatId) {
    console.warn("Warning: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. Please set them in the environment.");
  }
});

process.on("SIGTERM", () => {
  server.close(() => {
    console.log("SIGTERM received, server closed");
  });
});

async function sendTelegramVideo({
  video,
  file,
  caption = "",
  parseMode = "HTML",
}: {
  video?: string;
  file?: { buffer: Buffer; filename: string; mimeType: string };
  caption?: string;
  parseMode?: string;
}) {
  const form = new FormData();
  form.append("chat_id", telegramChatId);
  form.append("caption", caption);
  form.append("parse_mode", parseMode);

  if (video) {
    form.append("video", video);
  }

  if (file) {
    const blob = new Blob([file.buffer], { type: file.mimeType || "application/octet-stream" });
    form.append("video", blob, file.filename || "upload.mp4");
  }

  return telegramApiRequest("sendVideo", form);
}

async function telegramApiRequest(method: string, payload: Record<string, unknown> | FormData) {
  const response = await fetch(`https://api.telegram.org/bot${telegramBotToken}/${method}`, {
    method: "POST",
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
    headers: payload instanceof FormData ? undefined : { "Content-Type": "application/json" },
  });

  const data = await response.json();

  if (!response.ok || !data.ok) {
    throw new Error(data.description || `Telegram API request failed: ${response.status}`);
  }

  return data.result;
}

async function parseMultipartUpload(req: Request): Promise<{ fields: Record<string, string>; file?: { buffer: Buffer; filename: string; mimeType: string } }> {
  return new Promise((resolve, reject) => {
    const fields: Record<string, string> = {};
    let fileBuffer: Buffer[] = [];
    let fileName = "upload.bin";
    let mimeType = "application/octet-stream";
    let activeFile = false;

    const bb = busboy({ headers: req.headers });

    bb.on("field", (name: string, value: string) => {
      fields[name] = value;
    });

    bb.on("file", (_name: string, stream: NodeJS.ReadableStream, info: FileInfo) => {
      activeFile = true;
      fileName = info.filename || fileName;
      mimeType = info.mimeType || mimeType;

      stream.on("data", (chunk) => {
        fileBuffer.push(Buffer.from(chunk));
      });

      stream.on("end", () => {
        if (activeFile) {
          resolve({
            fields,
            file: {
              buffer: Buffer.concat(fileBuffer),
              filename: fileName,
              mimeType,
            },
          });
        }
      });
    });

    bb.on("finish", () => {
      if (!activeFile) {
        resolve({ fields });
      }
    });

    bb.on("error", (error) => reject(error));

    req.pipe(bb);
  });
}
