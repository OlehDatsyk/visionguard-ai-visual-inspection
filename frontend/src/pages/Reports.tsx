import { Download, Eye, FileText, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button, Card, ConfirmDialog, Empty, ErrorNote, Modal, PageHeader, Pagination, Spinner, useToast } from "../components/ui";
import { useApi, useAuthedImage } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, del, downloadFile } from "../services/api";
import type { Page, Report } from "../types";
import { formatBytes, formatDateTime } from "../utils/format";

function PdfPreview({ report, onClose }: { report: Report; onClose: () => void }) {
  const { src, failed } = useAuthedImage(`/reports/${report.id}/file`);
  return (
    <Modal title={report.title} wide onClose={onClose}>
      {failed && <ErrorNote message="The report could not be loaded." />}
      {!src && !failed && <Spinner label="Loading report" />}
      {src && <iframe title={`Preview of ${report.title}`} src={src} className="h-[75vh] w-full rounded border border-ink-700 bg-white" />}
    </Modal>
  );
}

export default function Reports() {
  const { workspace } = useSession();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [preview, setPreview] = useState<Report | null>(null);
  const [deleting, setDeleting] = useState<Report | null>(null);
  const { data, error, loading, reload } = useApi<Page<Report>>(workspace ? `/reports?workspace_id=${workspace.id}&page=${page}` : null);

  // Opens a report that has just been generated.
  useEffect(() => {
    const open = params.get("open");
    const match = data?.items.find((r) => r.id === open);
    if (match) {
      setPreview(match);
      setParams({}, { replace: true });
    }
  }, [params, data, setParams]);

  const download = (report: Report) => {
    downloadFile(`/reports/${report.id}/file?download=true`, `${report.title.replace(/[^\w\- ]+/g, "").trim() || "report"}.pdf`)
      .catch(() => toast("The download failed.", "error"));
  };

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <PageHeader title="Reports" description="PDF reports generated from your inspection records. Generate one from an analysed inspection." />
      <Card bodyClass="">
        {error && <div className="p-3"><ErrorNote message={error} onRetry={() => void reload()} /></div>}
        {loading && !data ? <Spinner /> : data?.items.length === 0 ? (
          <Empty icon={FileText} title="No reports yet" action={<Link to="/inspections"><Button>Open an inspection</Button></Link>}>Open an analysed inspection and choose Generate report.</Empty>
        ) : (
          <ul className="divide-y divide-ink-700">
            {data?.items.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <FileText className="h-5 w-5 shrink-0 text-text-3" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-text-1">{r.title}</div>
                  <div className="text-xs text-text-3">
                    <Link className="hover:text-text-1" to={`/inspections/${r.project_id}`}>{r.project_name}</Link>, {formatDateTime(r.created_at)}, {r.page_count} pages, {formatBytes(r.file_size)}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <Button small icon={Eye} onClick={() => setPreview(r)}>Preview</Button>
                  <Button small icon={Download} onClick={() => download(r)}>Download</Button>
                  <Button small variant="ghost" icon={Trash2} aria-label={`Delete ${r.title}`} onClick={() => setDeleting(r)} />
                </div>
              </li>
            ))}
          </ul>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />}
      </Card>
      {preview && <PdfPreview report={preview} onClose={() => setPreview(null)} />}
      {deleting && (
        <ConfirmDialog title="Delete this report?" confirmLabel="Delete" onClose={() => setDeleting(null)} body={`"${deleting.title}" will be permanently deleted. The inspection itself stays.`}
          onConfirm={() => void del(`/reports/${deleting.id}`).then(() => { setDeleting(null); void reload(); }).catch((e: ApiError) => toast(e.message, "error"))} />
      )}
    </div>
  );
}
