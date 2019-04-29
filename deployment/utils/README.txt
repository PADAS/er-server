Using curl for perf testing:

Get a bearer token for both systems, and call identical endpoints:

MAC-JayL-2:utils jayl$ curl -w "@curl-format.txt" -o /dev/null -H "Authorization: Bearer m5q0ogO7U8dw128aN6viyeZ9eE4S3R" -s https://garamba.pamdas.org/api/v1.0/subjects?bbox=29.18380737304688,4.050576786133467,29.81552124023438,4.282734218104703
    time_namelookup:  0.064024
       time_connect:  0.228710
    time_appconnect:  0.620516
   time_pretransfer:  0.620624
      time_redirect:  0.000000
 time_starttransfer:  1.673472
         time_total:  1.673814
          redirects:  0
      size_download:  20923
MAC-JayL-2:utils jayl$ 
MAC-JayL-2:utils jayl$ curl -w "@curl-format.txt" -o /dev/null -H "Authorization: Bearer mVv6MfASXHvlAHl9vzCfQ5zgyJJonT" -s https://garamba.apn.pamdas.org/api/v1.0/subjects?bbox=29.18380737304688,4.050576786133467,29.81552124023438,4.282734218104703
    time_namelookup:  0.025466
       time_connect:  0.219450
    time_appconnect:  0.628712
   time_pretransfer:  0.628808
      time_redirect:  0.000000
 time_starttransfer:  1.042676
         time_total:  1.242463
          redirects:  0
      size_download:  21051


Note the network latency, the delta between app contact, and it starting to return data, and delivering the payload. Because the net is variant, make sure you run it a number of times to get an understanding of average responses. We seem to have a delta in payload, I don't think that is significant, but we should understand the underlying reason for that.
