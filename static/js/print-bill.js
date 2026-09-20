// Prints a bill without leaving the page the user is on: the bill URL is
// loaded into a hidden iframe and that iframe is printed, so the sale/return
// record stays open behind the print dialog. The bill page keeps its own
// @page rules and its roll-height measurement, which run inside the frame
// exactly as they do when it's opened directly.
(function () {
  let frame = null;

  window.printBill = function (url) {
    if (!frame) {
      frame = document.createElement('iframe');
      frame.setAttribute('aria-hidden', 'true');
      frame.setAttribute('tabindex', '-1');
      // Parked off-screen rather than display:none or zero-sized: the bill has
      // to be laid out for its own height measurement to come out right, and
      // wide enough that the A4 variant isn't measured at roll width.
      frame.style.cssText = 'position:fixed;left:-9999px;top:0;width:220mm;height:400mm;border:0;';
      document.body.appendChild(frame);
    }

    frame.onload = function () {
      // A fresh load replaces the frame's window, so grab it after onload.
      const win = frame.contentWindow;
      win.focus();
      win.print();
    };
    // Printing the same bill twice in a row would otherwise set an identical
    // src, which doesn't reload and so never fires onload — nothing would
    // print the second time.
    frame.src = url + (url.indexOf('?') === -1 ? '?' : '&') + '_=' + Date.now();
  };
})();
