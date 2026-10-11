const axios = require("axios");
const fs = require("fs");
const path = require("path");
const moment = require("moment");
const https = require("https");

const url = `https://www.nseindia.com/content/historical/EQUITIES/$year/$month/cm$dateStringbhav.csv.zip`;

// Configure HTTPS Agent for SSL/TLS compatibility
const httpsAgent = new https.Agent({
  rejectUnauthorized: false,
  ciphers: 'DEFAULT:@SECLEVEL=1'
});

function getFileName(url) {
  const chunks = url.split("/");
  return chunks[chunks.length - 1];
}

function download(targetUrl) {
  const filename = getFileName(targetUrl);
  const filepath = path.resolve(__dirname, "data", filename);

  // Skip if file already downloaded
  if (fs.existsSync(filepath)) {
    return;
  }

  axios({
    url: targetUrl,
    method: "GET",
    responseType: "stream",
    httpsAgent: httpsAgent,
    timeout: 10000,
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Referer": "https://www.nseindia.com/"
    },
  })
    .then((response) => {
      if (response.status === 200) {
        const writer = fs.createWriteStream(filepath);
        response.data.pipe(writer);
        console.log("File downloaded:", filename);
      }
    })
    .catch((e) => {
      // Graceful error logging for missing archives/holidays
      console.log(`Notice: Could not fetch ${filename} (may be holiday or archive limit).`);
    });
}

// Only attempt download for the most recent 30 trading days to avoid thousands of legacy SSL requests
let start = moment().subtract(30, "days");
const urlSet = [];

while (start.isBefore(moment())) {
  start = start.add(1, "days");
  const day = start.format("dddd");
  const dateString = start.format("DDMMMyyyy").toUpperCase();

  if (day !== "Saturday" && day !== "Sunday") {
    const finalURL = url
      .replace("$dateString", dateString)
      .replace("$year", start.format("YYYY"))
      .replace("$month", start.format("MMM").toUpperCase());
    urlSet.push(finalURL);
  }
}

let i = 0;
const timer = setInterval(() => {
  if (i < urlSet.length) {
    download(urlSet[i]);
    i++;
  } else {
    clearInterval(timer);
  }
}, 500);
