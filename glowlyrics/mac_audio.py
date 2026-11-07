# Copyright © 2026 Tirhut LLC. All rights reserved.
"""macOS system-audio capture for beat detection, using Apple's ScreenCaptureKit
(macOS 13+). macOS asks once for "Screen & System Audio Recording" permission.

Only the audio stream is used, at the smallest possible video size. Samples are
analysed in memory for loudness/bass and immediately discarded; nothing is recorded,
stored, or sent anywhere. GlowLyrics' own sounds are excluded.
"""
import logging
import threading

import numpy as np

log = logging.getLogger("glowlyrics")

try:
    import objc
    import CoreMedia
    import ScreenCaptureKit as SCK
    from Foundation import NSObject
    AVAILABLE = True
except Exception as e:  # pragma: no cover - only on macOS with PyObjC
    log.info("ScreenCaptureKit not available: %s", e)
    AVAILABLE = False

PERMISSION_HELP = ("To pulse with the beat, allow GlowLyrics in System Settings → Privacy & "
                   "Security → Screen & System Audio Recording, then quit and reopen GlowLyrics. "
                   "Audio is analysed on your Mac only and never recorded or sent.")

_Output = None


def _output_class():
    """SCStreamOutput / SCStreamDelegate implementation (created lazily, once)."""
    global _Output
    if _Output is not None:
        return _Output
    protocols = []
    for name in ("SCStreamOutput", "SCStreamDelegate"):
        try:
            protocols.append(objc.protocolNamed(name))
        except Exception:
            pass

    class GlowLyricsAudioOutput(NSObject, protocols=protocols):  # noqa: N801
        def initWithSink_(self, sink):
            self = objc.super(GlowLyricsAudioOutput, self).init()
            if self is None:
                return None
            self._sink = sink
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, sbuf, kind):
            if kind != SCK.SCStreamOutputTypeAudio:
                return
            try:
                bb = CoreMedia.CMSampleBufferGetDataBuffer(sbuf)
                if bb is None:
                    return
                n = CoreMedia.CMBlockBufferGetDataLength(bb)
                frames = CoreMedia.CMSampleBufferGetNumSamples(sbuf)
                if n <= 0 or frames <= 0:
                    return
                status, data = CoreMedia.CMBlockBufferCopyDataBytes(bb, 0, n, None)
                if status != 0 or not data:
                    return
                samples = np.frombuffer(bytes(data), dtype=np.float32)
                # Float32, non-interleaved: first `frames` values are the left channel.
                self._sink(samples[:frames] if samples.size >= frames else samples)
            except Exception as e:  # pragma: no cover
                log.debug("audio buffer error: %s", e)

        def stream_didStopWithError_(self, stream, error):
            self._sink(None, error=str(error))

    _Output = GlowLyricsAudioOutput
    return _Output


class MacSystemAudio:
    """Starts/stops a ScreenCaptureKit audio stream; calls sink(mono_float32_array)."""

    def __init__(self, sink):
        self._sink = sink
        self._stream = None
        self._output = None
        self._lock = threading.Lock()
        self.running = False
        self.error = ""
        self.denied = False

    def _deliver(self, samples, error=None):
        if error:
            self.running = False
            self.error = error
            return
        self._sink(samples)

    def start(self):
        if not AVAILABLE or self.running:
            return
        self.error = ""

        def got_content(content, error):
            if error is not None or content is None:
                code = error.code() if error is not None else 0
                self.denied = code in (-3801, -3802) or "declin" in str(error).lower() \
                    or "permission" in str(error).lower() or "not authori" in str(error).lower()
                self.error = str(error)
                return
            try:
                displays = content.displays()
                if not displays:
                    self.error = "no display"
                    return
                filt = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(displays[0], [])
                conf = SCK.SCStreamConfiguration.alloc().init()
                conf.setCapturesAudio_(True)
                conf.setExcludesCurrentProcessAudio_(True)
                conf.setSampleRate_(48000)
                conf.setChannelCount_(2)
                conf.setWidth_(2)            # we don't want video: keep it tiny and slow
                conf.setHeight_(2)
                conf.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
                conf.setQueueDepth_(3)
                out = _output_class().alloc().initWithSink_(self._deliver)
                stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(filt, conf, out)
                ok, err = stream.addStreamOutput_type_sampleHandlerQueue_error_(
                    out, SCK.SCStreamOutputTypeAudio, None, None)
                if not ok:
                    self.error = str(err)
                    return

                def started(err2):
                    if err2 is not None:
                        self.error = str(err2)
                        self.denied = "declin" in str(err2).lower() or "-3801" in str(err2)
                        self.running = False

                with self._lock:
                    self._stream, self._output = stream, out
                    self.running = True
                stream.startCaptureWithCompletionHandler_(started)
            except Exception as e:  # pragma: no cover
                self.error = str(e)
                self.running = False

        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(got_content)

    def stop(self):
        with self._lock:
            stream, self._stream = self._stream, None
            self._output = None
            self.running = False
        if stream is not None:
            try:
                stream.stopCaptureWithCompletionHandler_(lambda err: None)
            except Exception:
                pass
