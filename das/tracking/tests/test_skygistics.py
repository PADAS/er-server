import pytest
import tracking.models.skygistics as skygistics

SKYQ3_FAULT_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <soap:Fault>
      <faultcode>UEsDBBQAAAAIAF28u0zrVfMrDQAAAAsAAAAKAAAAWmlwcGVkRmlsZSvOTyywCk4tKkstAgBQSwECFAAUAAgACABdvLtM61XzKw0AAAALAAAACgAAAAAAAAAAAAAAAAAAAAAAWmlwcGVkRmlsZVBLBQYAAAAAAQABADgAAAA1AAAAAAA=</faultcode>
      <faultstring>UEsDBBQAAAAIAF28u0zN/i6lGAIAALQGAAAKAAAAWmlwcGVkRmlsZb2VUU/bMBDH3/cp/ITYtEZO6qQpvFGKVmmIqgXtAaHpbF/baImdOW4p+/SzS+JOIA3WbTxETs73v/udfXbmD43FKvqCPJqj2RQCm2hqtNVCl00011CPtwJrW2h1QpzXDL+vsbE3CniJ19q5OkVDer3e0dKekjbchTYV2F+UE7WBspCkRLW0K7LQhgA5gwZ7GSNiBe7TGHggzt5YU6hl9I4QsF28kVYbNDa6MLryqox9PUehJZLjzsPF+OC0YOxE1Ws7teZjp54o209I4c2fd/nDzNmDxVZ17qp6LpLO+qh5T27pltKE8TsXihyV9lRyHmdIOQgpGNBFPmCDHBmNuUiGPBN+RU4oeaEST+4SP6mkeLGIFohm8h8DzXcbEHjaz6bLl/QPy3cJLpwZzV15te+30G4jXdXGNZFrlPHWovIv0Y36UdTPGHbDtd5NdjyUBp4kHtJ+yuM4yVPWHyxAgqAZipRL6IOI/5bHH4fANLnyWAiVx3LDE6wsfzMschz2hr9F0vbQX7oHlvsj+Js7pHOtHseAKw7DfXXCaLbeczevIQ3et3cEg3J/YWhdIihiV0bfX6lww3UV5XGoaCByWPA0XwiBTDDkCUthSAdSxijZMP3DirwZTWeLZghyCgYqdBvX7Dsgzv4HwL4lPoGSJRrXGAbbPmh/CYEhZvIABv8LIWMliV44sULjlr9dXH9Bi2/EGhDo3X4CUEsBAhQAFAAIAAgAXby7TM3+LqUYAgAAtAYAAAoAAAAAAAAAAAAAAAAAAAAAAFppcHBlZEZpbGVQSwUGAAAAAAEAAQA4AAAAQAIAAAAA</faultstring>
      <detail />
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
'''

SKYQ3_GET_REPLAY_DATA_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <getReplayDataResponse xmlns="http://tempuri.org/">
      <getReplayDataResult>UEsDBBQAAAAIAEAWqUz1+I+IrQQAAE4tAAAKAAAAWmlwcGVkRmlsZb2ay25bRwyGX8WLLOOAQw45ZLoymqIo0AZB0E03JyqKInVRxEDQZhX02TPSObpkLjzIYkYSLFuGjz/TP39eRsLPnr394c3PD7+9evj14X+EoPdA92h3AC/zg3D55enT44f3CyxpwbgQvgggdLkt9xhexBDt+gpsd2Q+PQdGJBDN14Llpw+///Hv46c/r58sy8N/7+/yb5Z33//1+M/T30/vfnz95i7YAs/h+eki+TlfJt8xX/34Uv4S8yuQL/8Vc6yZCVZmQt5Y0dRnxYATWLXBKisrX8O6g0os41EDdlEjcyEFENiRAgNMYJaGfHVlNtFCvhB34iwxjmfGVsptcb4K4cJsbdSkozONoO0OaUXVcFYC7kTVCCegtkxhNbJ4vNDKym3ECEkmIPa9gIMWYgUWbrMiwnhWxwyYrBRpYNluqc2cM2sCc8sMbGVGCxfCjbkjBYYJiYX9xOKcLUV4Me2EV3h4hoWmGWxllxmq+hD8+hCTyQTmlivwiVkklCknFPw4W4QJzC2boBNziljIGNh85iznOJ65aRerntNt1V2ZE/rayA+dwNzvHVII3xxnShNy0OkdUmbcWJV8v2AOY3Mv3kPwmofEofQLgna5y5UFJrD2R4p0SbmLFiLuxFchTmBu+cSqXzEt9RthR78WdTxz0yd4yzkpNRHb9iBgOAFV+vJFPLuC+r2v5JliPKrjCqJWqtfAV6+QDs84bLvDVpkhnZ0skV8pcuMTJ7C23CGsrAxlpu11EfkbOoG5P2wIp6oipx0da8DxzG4XQWWcE7YrhhjLBNZ+9yASq80D+zpOASbkHDo5x1INSLLDjHF47tHZJ6jpE5e5Pv/P24x0NOjhjF73UA32lHbiyoQT4tr3h5Tl+JUWyGLwa0aSJOOZm/4Qt+636thTe3OWFGECar97kMSV/XZ2PXlGnpBiXvsQy70JWPBLhQYYXt5iu33YmINebKEdVkXGCYixO8fnZntLLFU/sZRMJqBqf02CKKUZdKLKEcajNj1gi+q5byTr5L6KxgmIzqEEx3LIgZ1hUhUn5JN3KIEFMxmi3+KqpeEJxt7Z5c0+8hLn6DNbGL8U4bYp4MosVI5qgdupZjh+KcJNV4jr2MOxbBczq9/WWBy/FGFvhCALZVtjqRNfHr8MYe+8ItbLkNuuocksNiHnmj6hW3yrcyGQnZzT8esR8RaRZNX4rnFHxzZ+PSJe80DJrmOPG1+CMH49It4oETFVo7B/MES5Hup4Zud8kxQq5nYjSbmm4ARW6Y6XV3tQ/xSe8qw8IdWcc008DjlbOHVHtmn8NiR5I0Qur9XZoO3IVsdvQ5JnC8h0sYUofnxNdQJr/xwzNzCV7TZJQxi/C0neXuE2quZH9ajwCaz9piFYtdfV9qkaZWOekGGOG4TKZMGkjcrjdyDq9QhBqiOUhDtSSON3IOodS2Cq39zQqWFBxy9DtG0G51431as7v0AEG78VUe+wMrKdM2ynncEwfiui7igRSb9tlKA8wA9Kuc/hcHknZKZOK/XhVii2vXZAPv1RAIfXT3evPubf/vFwvEG+dyAO1Tub80/fXBzpJVt+fD5BfrfRVc+nj43n7U/8AlBLAQIUABQACAAIAEAWqUz1+I+IrQQAAE4tAAAKAAAAAAAAAAAAAAAAAAAAAABaaXBwZWRGaWxlUEsFBgAAAAABAAEAOAAAANUEAAAAAA==</getReplayDataResult>
    </getReplayDataResponse>
  </soap:Body>
</soap:Envelope>
'''

ENCODED_FIELD = '''UEsDBBQAAAAIALqJqEy71A0NDwAAAA0AAAAKAAAAWmlwcGVkRmlsZUssL0nPz0ssSq3KyC8FAFBLAQIUABQACAAIALqJqEy71A0NDwAAAA0AAAAKAAAAAAAAAAAAAAAAAAAAAABaaXBwZWRGaWxlUEsFBgAAAAABAAEAOAAAADcAAAAAAA=='''
DECODED_FIELD = 'awtgonarezhou'


LOGIN_RESULT = '''UEsDBBQAAAAIALURqUz5etvQkgEAADQCAAAKAAAAWmlwcGVkRmlsZT2QTW7bMBCFr+J9VYSk/ux14ihBZcmw1SBoFx3GZBwiEinQVFwVwSx6op6hvViHTVDgARzyDfnmo0hGeTqdnVcJS+Q5HJ2VXv94clNSpInIl0XCvzJg0MhBIwcOnaFCgIB9kGE6YQop7EetFWaQwR3mkMOfn79/XWIBBdxoqYw9Ygkl3LYcl7CkVeAKVnDlzYv2yBmQaneQwTiLnEI47LU3sl80ZAsgfbYmLLp5pBlSINXOHk2YFO0zINV0+W2bA6nybhqRF0Da9vJA5yWQLt0wOGXCjHwJpN26alrkKyC1yg06aP/KkKPA7LVpmzWxt71axPgT4X8JXh6eCf+4f54JdW0fnZdEet1rHfxkLQERqTfKTAPRbjrBGLv4pOdRKqK+3l1U0g/GRuw3MxLTa2f5oiPs7dW2uL+PmNsnp635HpGGj9SxqKVVEeq/Ub4bG+mN1ZFp02URZ9Ol9PIHFOy942Z+oJlQcKhqCv1GNop/YSWFiRQ6d6bRRQa7aQy6lyjoF+/KHEUBVcd57C+pShn/C1BLAQIUABQACAAIALURqUz5etvQkgEAADQCAAAKAAAAAAAAAAAAAAAAAAAAAABaaXBwZWRGaWxlUEsFBgAAAAABAAEAOAAAALoBAAAAAA=='''
LOGIN_RESULT_DECODED = '''2,password,0,awtgonarezhou,63,2586,1[0`0`Name~1`1`Time~2`2`Status~3`3`Speed~4`4`V~5`5`Â°C~6`6`Heading~7`7`IO1~8`8`IO2~9`9`Driver~10`10`Location~11`11`Serial Nr~12`12`Unit Type~13`13`Longitude~14`14`Latitude~15`15`Group~16`16`Place~17`17`Commodity~18`18`REGNO~19`19`Odometer|0~1~2~4|NONE[0`Old Units~1`Ztrack~2`gSky~5`Enfora~6`Fleetrunner~7`Iridium~8`MT2000/Keypad~9`FR/Garmin~10`MT2000~11`Skywave~12`IDP6XX~13`Phoenix~15`m-Sky Land~16`Phoenix~17`m-Sky Marine~18`MT4~19`MT3000+~20`m-Sky Hybrid~21`GL200_300~22`IDP7XX~23`Tower~24`Ruptela~25`GV75~26`GT1100~27`GT301'''

UNIT_LIST_RESULT = ''''''
UNIT_LIST_RESULT_DECODED = '''Aug 2016_Chilojo_GNP 19`2018-04-18 20:00:32`Moving`0`7`18`0` `1`1`4211.3 km SE GPS Origin; .9 km S Fishan(ZIM)`28195`32.034133`-21.4433`0`1524107444`2018-04-19 05:10:41`4178`01144913SKY0BD2`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1526`100000`N`5.1.7.11336` ` `Release``0`0`0`0`0`0`0.0` ``~Aug 2016_Chipinda_GNP 18`2018-04-18 20:00:32`Moving`0`7`20`0` `1`1`4189.7 km SE GPS Origin; 1.3 km S Chipinda Pools(ZIM)`28194`31.898383`-21.273967`0`1524110192`2018-04-19 05:56:31`4178`01144901SKYDB96`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1540`100000`N`5.1.7.11336` ` `Release``0`0`0`0`0`0`0.0` ``~Aug 2016_Mabalauta_GNP 17`2018-04-12 06:00:32`Moving`0`7`22`0` `1`1`4174.4 km SE GPS Origin; 13.4 km E Chikombedzi(ZIM)`28193`31.43405`-21.7369`0`1523538997`2018-04-12 15:16:37`4178`01145051SKY3684`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`980`100000`N`5.1.7.11336` ` `Release``0`0`0`0`0`0`0.0` ``~Aug 2016_Nyamtongwe_GNP 15`2018-03-29 03:00:32`Moving`0`7`26`0` `1`1`4115.1 km SE GPS Origin; N1; 14.3 km SW Mookgophong(RSA)`25658`28.624217`-24.620683`0`1522318063`2018-03-29 12:07:43`4178`01099317SKY2146`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0` ` ` `5.1.7.11336`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~Aug 2016_Tshingwedzi_GNP 16`2018-04-18 20:00:32`Moving`0`7`21`0` `1`1`4192.8 km SE GPS Origin; 9.4 km E Chibgwedziva(ZIM)`28197`31.862367`-21.387217`0`1524107257`2018-04-19 05:07:37`4178`01144903SKYE3A0`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1526`100000`N`5.1.7.11336` ` `Release``0`0`0`0`0`0`0.0` ``~GON09`2018-04-18 14:27:56`Moving`0`7`23`0``1`1`4205.5 km SE GPS Origin; 17 km S Rupangwana(ZIM)`25657`32.149667`-21.1503`0`1524101266`2018-04-19 03:27:45`4178`01099301SKYE0F6`0`22```Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`2016-09-28 07:46:28`1970-01-01 02:00:00`No Destination```````````Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1526`100000`N`4.3.5.8338`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~GON10_not deployed`2018-01-19 20:02:02`Moving`0`7`19`0` `1`1`4210.9 km SE GPS Origin; 4.8 km W Motetema(RSA)`25650`29.415917`-25.09855`0`1516435703`2018-01-20 10:08:23`4178`01099302SKY64FB`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`2016-09-28 07:46:46`1970-01-01 02:00:00`No Destination```````````Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0` ` ` `4.3.5.8338`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~GON11`2018-04-18 14:30:02`Moving`0`7`21`0``1`1`4196.7 km SE GPS Origin; 13.4 km SE Chibgwedziva(ZIM)`25659`31.883133`-21.423367`0`1524101403`2018-04-19 03:30:03`4178`01099313SKY1132`0`22```Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`2016-09-28 07:47:05`1970-01-01 02:00:00`No Destination```````````Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1526`100000`N`4.3.5.8338`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~GON12`2018-03-28 22:01:03`Moving`0`7`25`0``1`1`4076.3 km SE GPS Origin; 5.8 km SW Chamnanga(ZIM)`25656`30.03205`-22.159667`0`1522314084`2018-03-29 11:01:24`4178`01099314SKY9537`0`22```Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`2016-09-28 07:47:24`1970-01-01 02:00:00`No Destination```````````Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0` ` ` `4.3.5.8338`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~GON14`2018-04-18 14:32:50`Moving`0`7`21`0``1`1`4190.4 km SE GPS Origin; 20.8 km NE Mabala(ZIM)`25652`31.588533`-21.77865`0`1524101571`2018-04-19 03:32:51`4178`01099324SKYBD69`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`2016-09-28 07:47:51`1970-01-01 02:00:00`No Destination```````````Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1526`100000`N`4.3.5.8338`1.0.3-11/20`basicelephant`Release``0`0`0`0`0`0`0.0` ``~Oct 2016_Snared_GNP 20`2018-04-18 21:00:51`Moving`0`7`21`0` `1`1`4219.4 km SE GPS Origin; 23.8 km NE Malvernia(MOZ)`28196`31.827533`-21.915067`0`1524111113`2018-04-19 06:11:53`4178`01144911SKY03C8`0`22`3200``Semi Truck.png`23`````Input 3 Closed`Input 4 Closed`0`0`0`0%`0%`1970-01-01 02:00:00`1970-01-01 02:00:00````99`99`OK`OK``0`1970-01-01 02:00:00`0`1970-01-01 02:00:00`1970-01-01 02:00:00`Green`10000`Green`10000`10000`10000`Green`10000`1970-01-01 02:00:00`1970-01-01 02:00:00`No Destination`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`Inactive`0`0`No`0`0`No`No`Inactive`Normal`Normal`False`1970-01-01 02:00:00`1970-01-01 02:00:00````0`1540`100000`N`5.1.7.11336` ` `Release``0`0`0`0`0`0`0.0` ``'''

REPLAY_LIST_RESULT_DECODED = '''6$$REPLAYDATA,2018-04-26 23:00:32^Moving^0^7^20^32.0389333333333^-21.43405^0^^0^0^255^0^0^1524783632^4211.2 km SE GPS Origin; .2 km NE Fishan(ZIM)^^^^1524783632^^,2018-04-26 19:00:32^Moving^0^7^31^32.01785^-21.4512333333333^0^^0^0^255^0^0^1524769232^4210.3 km SE GPS Origin; 2.7 km SW Fishan(ZIM)^^^^1524769232^^,2018-04-26 15:00:32^Moving^0^7^33^32.00745^-21.4304333333333^0^^0^0^255^0^0^1524754832^4208.2 km SE GPS Origin; 3.2 km W Fishan(ZIM)^^^^1524754832^^,2018-04-26 11:00:32^Moving^0^7^25^32.0018333333333^-21.4349^0^^0^0^255^0^0^1524740432^4208 km SE GPS Origin; 3.7 km W Fishan(ZIM)^^^^1524740432^^,2018-04-26 07:00:32^Moving^0^7^16^31.9868833333333^-21.4454^0^^0^0^255^0^0^1524726032^4207.2 km SE GPS Origin; 5.4 km W Fishan(ZIM)^^^^1524726032^^,2018-04-26 03:00:32^Moving^0^7^18^31.9935166666667^-21.4614333333333^0^^0^0^255^0^0^1524711632^4208.7 km SE GPS Origin; 5.4 km SW Fishan(ZIM)^^^^1524711632^^'''


def test_decode_soap_fault():
    client = skygistics.SkygisticsQ3Client()
    fault = client._get_fault(SKYQ3_FAULT_RESPONSE)
    assert fault.code == 'soap:Server'


def test_decode_field():
    client = skygistics.SkygisticsQ3Client()
    assert client.decode_field(ENCODED_FIELD) == DECODED_FIELD


def est_encode_field():
    client = skygistics.SkygisticsQ3Client()
    assert client.encode_field(DECODED_FIELD) == ENCODED_FIELD


def test_roundtrip_encode():
    client = skygistics.SkygisticsQ3Client()
    initial = 'a really big string'
    encoded = client.encode_field(initial)
    assert initial == client.decode_field(encoded)


def test_find_ge_replay_node():
    client = skygistics.SkygisticsQ3Client()

    assert client.get_action_result_from_response_body(
        'getReplayDataResult',
        SKYQ3_GET_REPLAY_DATA_RESPONSE).startswith('UEsDBBQAAAAIAEAWqUz1+I+IrQQAAE4tAAAKAAAAWmlwcGVkRml')


def test_find_soap_fault_node():
    client = skygistics.SkygisticsQ3Client()
    assert client.get_action_result_from_response_body(
        'faultcode',
        SKYQ3_FAULT_RESPONSE).startswith('UEsDBBQAAAAIAF28u0zrVfMrDQAAAAsAAAAKAAAA')


def test_parse_unit_list():
    client = skygistics.SkygisticsQ3Client()

    for unit in client._parse_unitlist_from_result(UNIT_LIST_RESULT_DECODED):
        assert unit.name


def test_parse_company():
    client = skygistics.SkygisticsQ3Client()

    company = client._parse_company_from_result(LOGIN_RESULT_DECODED)
    assert company.company_id == 2586


def test_parse_replay_data():
    client = skygistics.SkygisticsQ3Client()
    observation_count = 0
    for observation in client._parse_replay_data_from_result(REPLAY_LIST_RESULT_DECODED):
        if isinstance(observation, skygistics.ReplayResult):
            assert observation.count == 6
            assert observation_count == 0
        else:
            assert observation_count > 0
            assert observation.time
            assert observation.temperature
            assert observation.latitude
        observation_count += 1
    assert observation_count > 0
