import { useAuth } from "@/lib/auth";

/**
 * Ruang lingkup HR/atasan = memegang salah satu hak lanjutan Absensi
 * (approve/edit/export/delete). Karyawan biasa (view + create) hanya melihat
 * tab self-service; backend juga membatasi data ke karyawan itu sendiri
 * (bukan hanya menyembunyikan tab).
 */
export const useAttendanceScope = () => {
  const { can, isSuperAdmin } = useAuth();
  const hrScope =
    Boolean(isSuperAdmin) ||
    can("attendance", "approve") ||
    can("attendance", "edit") ||
    can("attendance", "export") ||
    can("attendance", "delete");
  return { hrScope, selfOnly: !hrScope };
};
