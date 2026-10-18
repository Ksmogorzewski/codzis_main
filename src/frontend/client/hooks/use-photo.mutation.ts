import { useMutation, useQueryClient } from "@tanstack/react-query";
import { shrinkPhoto, uploadToS3 } from "@/lib/account";
import { apiDelete, apiPost, apiPut, unwrap } from "@/lib/api";
import { meKey } from "@/lib/query-keys";
import { MeSchema, PhotoUploadSchema } from "@/lib/schemas";

// Nowe zdjęcie profilowe: zmniejszenie w przeglądarce (JPEG) -> POST /api/me/photo (formularz S3)
// -> upload prosto do S3 -> PUT /api/me/photo {key} -> Me.
export function useUploadPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const photo = await shrinkPhoto(file).catch(() => {
        throw new Error("Nie udało się odczytać tego zdjęcia. Wybierz inne.");
      });
      const form = unwrap(await apiPost("/api/me/photo", { contentType: "image/jpeg" }, PhotoUploadSchema));
      if (!(await uploadToS3(form.upload, photo))) throw new Error("Nie udało się wysłać zdjęcia. Spróbuj ponownie.");
      return unwrap(await apiPut("/api/me/photo", { key: form.key }, MeSchema));
    },
    onSuccess: (me) => queryClient.setQueryData(meKey(), me),
  });
}

// DELETE /api/me/photo -> Me bez zdjęcia (także zdjęcia z Google)
export function useDeletePhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await apiDelete("/api/me/photo", MeSchema)),
    onSuccess: (me) => queryClient.setQueryData(meKey(), me),
  });
}
