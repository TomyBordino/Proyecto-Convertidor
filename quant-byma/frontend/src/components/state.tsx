import { Card, CardContent } from "@/components/ui/card";

export function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">{label}</div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Card className="border-negative/40">
      <CardContent className="p-4 text-sm">
        <p className="font-medium text-negative">No se pudieron cargar los datos</p>
        <p className="mt-1 text-muted-foreground">{message}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          ¿Está corriendo el backend? <code>cd backend &amp;&amp; uvicorn app.main:app --reload</code>
        </p>
      </CardContent>
    </Card>
  );
}
