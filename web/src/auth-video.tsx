import React, {useEffect, useRef} from 'react';

/** Foreground playback recovery; browsers retain control when the tab is hidden. */
export function AuthVideo(){
  const ref=useRef<HTMLVideoElement>(null);
  useEffect(()=>{
    const video=ref.current!;
    let disposed=false, previous=-1, stalled=0;
    const resume=()=>{if(!disposed && document.visibilityState==='visible')video.play().catch(()=>{});};
    const events=['pause','ended','loadeddata','canplay'];
    events.forEach(event=>video.addEventListener(event,resume));
    document.addEventListener('visibilitychange',resume);
    window.addEventListener('pageshow',resume);
    const timer=window.setInterval(()=>{
      if(document.visibilityState!=='visible')return;
      if(video.paused)resume();
      stalled=video.currentTime===previous?stalled+1:0;previous=video.currentTime;
      if(stalled>=5 && video.readyState<2){stalled=0;video.load();resume();}
    },1000);
    resume();
    return()=>{disposed=true;clearInterval(timer);events.forEach(event=>video.removeEventListener(event,resume));document.removeEventListener('visibilitychange',resume);window.removeEventListener('pageshow',resume);};
  },[]);
  return <video ref={ref} className="auth-network-video" src="/media/auth-network.mp4?v=brand-orbits-20261010" autoPlay muted loop playsInline preload="auto" aria-hidden="true"/>;
}
