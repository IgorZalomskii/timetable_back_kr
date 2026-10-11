// Opt-in local QA observation only. No storage, network or user data collection.
if (new URLSearchParams(location.search).has('_qa') && 'PerformanceObserver' in window) {
 let cls=0;
 document.documentElement.dataset.qaCls='0';
 try {
  new PerformanceObserver(list=>{
   for(const entry of list.getEntries()){
    const shift=entry as PerformanceEntry & {value:number;hadRecentInput:boolean};
    if(!shift.hadRecentInput)cls+=shift.value;
   }
   document.documentElement.dataset.qaCls=String(cls);
  }).observe({type:'layout-shift',buffered:true});
 } catch { document.documentElement.dataset.qaCls='unsupported'; }
}
