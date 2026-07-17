"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  messageFromError,
  RequestTimeoutError,
  UnknownMutationOutcomeError,
} from "@/lib/httpUtils";

import {
  createCalibration,
  loadCalibrationCatalog,
} from "../lib/calibrationApiUtils";
import {
  calibrationProfilesFromPayload,
  sourceImagesFromPayload,
} from "../lib/calibrationUtils";

export default function useCalibrationCatalog() {
  const [profiles, setProfiles] = useState([]);
  const [sourceImages, setSourceImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [createPending, setCreatePending] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createRequiresRefresh, setCreateRequiresRefresh] = useState(false);
  const mountedRef = useRef(false);
  const loadGenerationRef = useRef(0);
  const loadControllerRef = useRef(null);
  const createControllerRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      loadControllerRef.current?.abort();
      createControllerRef.current?.abort();
    };
  }, []);

  const load = useCallback(async () => {
    loadControllerRef.current?.abort();
    const controller = new AbortController();
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    loadControllerRef.current = controller;
    setLoading(true);

    try {
      const [profilePayload, sourcePayload] = await loadCalibrationCatalog(
        controller.signal,
      );
      if (
        !mountedRef.current
        || controller.signal.aborted
        || generation !== loadGenerationRef.current
      ) {
        return false;
      }
      setProfiles(calibrationProfilesFromPayload(profilePayload));
      setSourceImages(sourceImagesFromPayload(sourcePayload));
      setLoadError("");
      setCreateError("");
      setCreateRequiresRefresh(false);
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (
        mountedRef.current
        && generation === loadGenerationRef.current
      ) {
        setLoadError(messageFromError(
          error,
          error instanceof RequestTimeoutError
            ? "讀取相機校正資料逾時，請重新讀取。"
            : "讀取相機校正資料失敗。",
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
        if (mountedRef.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = useCallback(async (payload) => {
    if (createControllerRef.current || createRequiresRefresh) return null;
    const controller = new AbortController();
    createControllerRef.current = controller;
    setCreatePending(true);
    setCreateError("");
    setCreateRequiresRefresh(false);

    try {
      const profile = await createCalibration(
        payload,
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return null;
      setProfiles((current) => [
        profile,
        ...current.filter(
          (item) => item.calibration_id !== profile.calibration_id,
        ),
      ]);
      return profile;
    } catch (error) {
      if (error?.name === "AbortError" && !mountedRef.current) return null;
      if (mountedRef.current) {
        const unknown = error instanceof UnknownMutationOutcomeError;
        setCreateRequiresRefresh(unknown);
        setCreateError(unknown
          ? `${error.message} 請先重新讀取清單，勿立即重送。`
          : messageFromError(
            error,
            "建立校正檔案失敗。",
          )
        );
      }
      return null;
    } finally {
      if (createControllerRef.current === controller) {
        createControllerRef.current = null;
        if (mountedRef.current) setCreatePending(false);
      }
    }
  }, [createRequiresRefresh]);

  return {
    profiles,
    sourceImages,
    loading,
    loadError,
    createPending,
    createError,
    createRequiresRefresh,
    load,
    create,
    clearCreateError: () => setCreateError(""),
  };
}
