import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { clientRejection, Dropzone } from "../components/Dropzone";
import { FindingDetail } from "../components/FindingPanel";
import { ImageViewer } from "../components/ImageViewer";
import { BandBadge, ReviewBadge, ToastProvider } from "../components/ui";
import { SessionProvider } from "../hooks/useSession";
import { api, ApiError, hasToken, setToken } from "../services/api";
import type { Finding } from "../types";
import { categoryLabel, formatBytes, pretty, scoreName } from "../utils/format";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const FINDING: Finding = {
  id: "f1", image_id: "i1", code: "F-AAAA-01", category: "crack_like", finding_type: "potential_defect", score: 0.82,
  score_type: "heuristic_anomaly", confidence_band: "medium", x: 10, y: 20, width: 100, height: 40,
  polygon: [[10, 20], [110, 20], [110, 60]], method: "Morphological black-hat", explanation: "A dark mark.",
  metrics: { length_px: 90 }, review_status: "unreviewed", created_at: "2026-11-07T10:00:00Z", updated_at: "2026-11-07T10:00:00Z",
  project_id: "p1", project_name: "P", image_filename: "a.png", reviews: [],
};

function routed(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider><ToastProvider><App /></ToastProvider></SessionProvider>
    </MemoryRouter>,
  );
}

describe("formatting", () => {
  it("labels values", () => {
    expect(pretty("false_positive")).toBe("False positive");
    expect(categoryLabel("crack_like")).toBe("Crack-like");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(scoreName("heuristic_anomaly")).toBe("Anomaly score");
    expect(scoreName("model_confidence")).toBe("Model confidence");
  });
});

describe("upload checks", () => {
  it("rejects unsupported and oversized files on the client", () => {
    expect(clientRejection(new File(["x"], "a.png"))).toBeNull();
    expect(clientRejection(new File(["x"], "a.exe"))).toMatch(/JPEG/);
    expect(clientRejection(new File([], "a.png"))).toMatch(/empty/);
    const big = new File(["x"], "b.png");
    Object.defineProperty(big, "size", { value: 21 * 1024 * 1024 });
    expect(clientRejection(big)).toMatch(/Larger/);
  });

  it("passes dropped and selected files to its handler", async () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} />);
    const file = new File(["x"], "photo.png", { type: "image/png" });
    await userEvent.upload(screen.getByTestId("file-input"), file);
    expect(onFiles).toHaveBeenCalledWith([file]);
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [file] } });
    expect(onFiles).toHaveBeenCalledTimes(2);
  });
});

describe("api client", () => {
  it("sends the bearer token and returns JSON", async () => {
    setToken("abc");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ok: true }));
    await expect(api("/x")).resolves.toEqual({ ok: true });
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBe("Bearer abc");
    setToken(null);
  });

  it("clears the session after a 401", async () => {
    setToken("expired");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "Not authenticated" }, 401));
    await expect(api("/x")).rejects.toBeInstanceOf(ApiError);
    expect(hasToken()).toBe(false);
  });

  it("turns network failures and rate limits into readable errors", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("failed"));
    await expect(api("/x")).rejects.toThrow(/could not be reached/);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "x" }, 429));
    await expect(api("/x")).rejects.toThrow(/Too many requests/);
  });
});

describe("confidence display", () => {
  it("shows a text label and not only a colour", () => {
    render(<><BandBadge band="unverified" /><ReviewBadge status="false_positive" /></>);
    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(screen.getByText("False positive")).toBeInTheDocument();
  });
});

describe("authentication routes", () => {
  it("redirects a signed-out visitor to sign in", async () => {
    routed("/analytics");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("signs in and shows the empty dashboard, with values from the API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) return json({ access_token: "t", expires_in: 60, user: { id: "u", email: "a@example.com", full_name: "Ada Test", created_at: "" } });
      if (url.endsWith("/workspaces")) return json([{ id: "w", name: "My workspace", is_demo: false, created_at: "" }]);
      if (url.includes("/analytics/overview")) return json({
        totals: { inspections: 0, images_analysed: 0, potential_defects: 0, requiring_review: 0 }, recent_projects: [],
        defect_distribution: [], inspection_trend: [], frequent_categories: [], recent_reports: [],
      });
      return json({}, 404);
    });
    routed("/");
    await userEvent.type(await screen.findByLabelText("E-mail"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("No inspections yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explore demo data" })).toBeInTheDocument();
    expect(screen.getByText("Ada Test")).toBeInTheDocument();
    for (const name of ["Overview", "New Inspection", "Inspection History", "Image Comparison", "Defect Analysis", "Reports", "Analytics", "Model Information", "Settings"]) {
      expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name })).toBeInTheDocument();
    }
    setToken(null);
  });

  it("shows a server error on failed sign-in", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => json({ detail: "Incorrect e-mail or password." }, 401));
    routed("/login");
    await userEvent.type(await screen.findByLabelText("E-mail"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect e-mail or password.");
  });
});

describe("finding review", () => {
  it("records a decision with its note", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PATCH") return json({ ...FINDING, review_status: "false_positive", reviews: [{ id: "r", decision: "false_positive", note: "A seam", created_at: "2026-11-07T10:00:00Z" }] });
      return json(FINDING);
    });
    const onChange = vi.fn();
    render(<ToastProvider><FindingDetail finding={FINDING} onChange={onChange} /></ToastProvider>);
    expect(screen.getByText(/not a probability/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Review note/), "A seam");
    await userEvent.click(screen.getByRole("button", { name: "False positive" }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ decision: "false_positive", note: "A seam" });
    expect(await screen.findByText("Decision history")).toBeInTheDocument();
  });
});

describe("image viewer", () => {
  const renderViewer = (onSelect = vi.fn()) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(new Blob(["x"]), { status: 200 }));
    render(<ImageViewer imageId="i1" width={400} height={300} hasProcessed objects={[{
      id: "o1", image_id: "i1", label: "cup", confidence: 0.8, confidence_band: "high", x: 1, y: 2, width: 50, height: 50,
      polygon: null, segmentation_method: null, model_name: "m",
    }]} findings={[FINDING]} selectedId={null} onSelect={onSelect} />);
    return onSelect;
  };

  it("draws overlays and lets them be toggled", async () => {
    renderViewer();
    expect(screen.getByText("cup 0.80")).toBeInTheDocument();
    expect(screen.getByText("Crack-like")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Objects"));
    expect(screen.queryByText("cup 0.80")).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Findings"));
    expect(screen.queryByText("Crack-like")).not.toBeInTheDocument();
  });

  it("has working zoom controls", async () => {
    renderViewer();
    await userEvent.click(screen.getByLabelText("Reset zoom to 100%"));
    expect(screen.getByText("100%")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Zoom in"));
    expect(screen.getByText("125%")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Zoom out"));
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("selects a finding when its region is clicked", async () => {
    const onSelect = renderViewer();
    await userEvent.click(screen.getByText("Crack-like"));
    expect(onSelect).toHaveBeenCalledWith("f1");
  });
});
