(() => {
  const BASE_W = 1240;
  const BASE_H = 440;
  const MOBILE_PORTRAIT_QUERY = '(max-width: 600px) and (orientation: portrait)';
  const MOBILE_CAMERA_ZOOM = 2;

  const frame = document.getElementById('gameFrame');
  const canvas = document.getElementById('cv');
  if (!frame || !canvas) return;

  function syncMobileCanvasSize() {
    const isMobilePortrait = window.matchMedia(MOBILE_PORTRAIT_QUERY).matches;
    if (!isMobilePortrait) {
      canvas.width = BASE_W;
      canvas.height = BASE_H;
      return;
    }

    const frameWidth = frame.clientWidth || canvas.clientWidth || BASE_W;
    const frameHeight = frame.clientHeight || canvas.clientHeight || BASE_H;
    const zoomedWidth = Math.round(BASE_W / MOBILE_CAMERA_ZOOM);
    const zoomedMinHeight = Math.round(BASE_H / MOBILE_CAMERA_ZOOM);
    const nextHeight = Math.max(zoomedMinHeight, Math.round(zoomedWidth * frameHeight / frameWidth));

    canvas.width = zoomedWidth;
    canvas.height = nextHeight;
  }

  syncMobileCanvasSize();
})();
