import { api } from "@/lib/api";

const filenameFrom = (disposition, fallback) => {
  if (!disposition) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8) return decodeURIComponent(utf8[1].replace(/"/g, ""));
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1] : fallback;
};

/**
 * Unduh berkas biner (PDF / Excel) melalui axios agar header Authorization terkirim.
 */
export const downloadFile = async (url, fallbackName, config = {}) => {
  const res = await api.get(url, { ...config, responseType: "blob" });
  const name = filenameFrom(
    res.headers?.["content-disposition"] || res.headers?.["Content-Disposition"],
    fallbackName
  );
  const objectUrl = window.URL.createObjectURL(res.data);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1500);
  return name;
};

export default downloadFile;
