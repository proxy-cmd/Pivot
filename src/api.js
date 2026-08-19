import axios from "axios";

// A relative URL keeps the packaged app on the same origin as the API. Vite
// proxies it locally; VITE_API_URL is only needed for a separately hosted API.
const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const API_UNAVAILABLE_MESSAGE = 'Cannot reach the Pivot API. Start it with "npm run api".';
let accessToken = null;
let refreshPromise = null;

export const api = axios.create({ baseURL: API_URL, withCredentials: true });

export function getAccessToken() {
  return accessToken;
}
export function setAccessToken(token) {
  accessToken = token || null;
}

async function refreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = api
    .post("/api/auth/refresh", null, { skipAuthRefresh: true })
    .finally(clearRefreshRequest);

  return refreshPromise;
}


function clearRefreshRequest() {
  refreshPromise = null;
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const failedRequest = error.config;
    if (!shouldRefreshSession(error, failedRequest)) {
      return Promise.reject(error);
    }

    failedRequest._retry = true;

    try {
      await refreshAccessToken();
      return api(failedRequest);
    } catch (refreshError) {
      expireSession();
      return Promise.reject(refreshError);
    }
  },
);


function shouldRefreshSession(error, request) {
  const unauthorized = error.response?.status === 401;
  const isRefreshRequest = request?.skipAuthRefresh;
  const alreadyRetried = request?._retry;

  return unauthorized && !isRefreshRequest && !alreadyRetried;
}


function expireSession() {
  setAccessToken(null);
  window.dispatchEvent(new CustomEvent("pivot:session-expired"));
}

export const auth = {
  async restore() {
    await refreshAccessToken();
    return (await api.get("/api/auth/me")).data;
  },
  login() {
    window.location.assign(`${API_URL}/api/auth/google/login`);
  },
  async logout() {
    try {
      await api.post("/api/auth/logout", null, { skipAuthRefresh: true });
    } finally {
      setAccessToken(null);
    }
  },
};

export async function request(path, options = {}) {
  try {
    const response = await api(buildRequest(path, options));
    return response.data;
  } catch (error) {
    throw requestError(error, "Request failed");
  }
}

export async function downloadFile(path) {
  try {
    const response = await api.get(path, { responseType: "blob" });
    saveBrowserDownload(response);
  } catch (error) {
    throw requestError(error, "Download failed");
  }
}


function buildRequest(path, options) {
  return {
    url: path,
    method: options.method || "GET",
    data: options.body,
    headers: options.headers,
  };
}


function requestError(error, label) {
  if (!error.response) {
    return new Error(API_UNAVAILABLE_MESSAGE);
  }

  const status = error.response.status;
  const detail = error.response.data?.detail;
  return new Error(errorMessage(detail, `${label} (${status}).`));
}


function errorMessage(detail, fallback) {
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .join(" ");
  }

  if (detail && typeof detail === "object") {
    return detail.message || detail.error || detail.reason || fallback;
  }

  return fallback;
}


function saveBrowserDownload(response) {
  const filename = downloadFilename(response.headers["content-disposition"]);
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}


function downloadFilename(disposition = "") {
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || "pivot-download";
}
