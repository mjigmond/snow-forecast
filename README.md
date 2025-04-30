### Snow Forecast Tool

Typical weather forecasts only cover well populated places but, if you're like me, and enjoy a cross country ski experience in remote areas, it helps to have a targeted forecast. Sure, you can always buy an app but it's less satisfying and at the end of the day, they all use a blend of existing models so you can always make your own blender recipe.

## The Basics
1. FastAPI based app that pulls the most recent model data (HRRR, GFS, AIFS) and generates forecast data for your area of interest.
2. Uses [Herbie](https://herbie.readthedocs.io/en/stable/) to subset variables of interest.
3. Can send email-to-text to major networks cell phone numbers (AT&T, T-Mobile, Verizon), but note that AT&T will discontinue the service starting June 17, 2025. You will need to setup a `.env` file with email credentials, such as:
```shell
EMAIL_USER = user@email-provider.com
EMAIL_PASS = app_type_password
# If using Gmail, see https://support.google.com/mail/answer/185833?hl=en for app passwords.
```
4. Sample request using a polygon geometry (WKT):
```json
{
  "name": "Peaceful Valley",
  "attime": "2025-05-02T06:00:00-06:00",
  "models": [
    "hrrr",
    "gfs",
    "aifs"
  ],
  "geometry": "Polygon ((-105.50254300231370053 40.13402149756592507, -105.54914528750731506 40.14002769655503755, -105.56878609735900909 40.14371305582209004, -105.58092768890368518 40.14084668255714661, -105.58896256566123384 40.14248462494526848, -105.59521191425039888 40.14603336465168582, -105.60199692129009463 40.15531380743114198, -105.61038890368128307 40.15981709469399163, -105.62128062550813468 40.16200039919328191, -105.63663616775583876 40.16554811925974633, -105.65074184028570414 40.16841345011864206, -105.66395474873137061 40.17073291508270927, -105.66895422760273959 40.1700507277331198, -105.67091830858791468 40.16773123945620227, -105.67145396703840277 40.16363783149257216, -105.66841856915220887 40.16104521211389056, -105.66681159380073041 40.1574972567353754, -105.66091935084520514 40.15613260914767579, -105.65574131915701628 40.15162907753074251, -105.64806354803320687 40.15053726731454731, -105.642885516345018 40.14794414770914699, -105.63449353395382957 40.14111967569738937, -105.62985116071615721 40.13811669082588907, -105.62967260789929469 40.13251986486893941, -105.62824418536465032 40.12869737737735676, -105.62467312902798255 40.12651300229108386, -105.60788916424559147 40.12378243472166162, -105.59021243537905832 40.11832097055105351, -105.57092873116103249 40.11804788582660564, -105.54503857272011658 40.11654590023795208, -105.52379078751690145 40.12036907102559979, -105.50236444949688064 40.12842433433039702, -105.50236444949688064 40.12842433433039702, -105.50254300231370053 40.13402149756592507))",
  "recipients": [
    {
      "number": 0123456789,
      "network": "verizon"
    }
  ]
}
```
5. Sample request using lat/lon:
```json
{
  "name": "Peaceful Valley",
  "attime": "2025-05-02T06:00:00-06:00",
  "models": [
    "hrrr",
    "gfs",
    "aifs"
  ],
  "lat": 40.139,
  "lon": -105.591,
  "recipients": [
    {
      "number": 0123456789,
      "network": "verizon"
    }
  ]
}
```
6. Save a request to a file (`forecast.json`) and run
```shell
curl -s -H "Content-Type: application/json" -X POST http://localhost:8008/forecast -d@forecast.json | jq
```
7. Sample response
```json
{
  "name": "Peaceful Valley",
  "attime": "2025-05-02T06:00:00-06:00",
  "forecast": [
    {
      "model": "hrrr",
      "min": 0.5708661435735226,
      "max": 3.562598478562832,
      "mean": 1.7063249759896244,
      "nan_reason": null
    },
    {
      "model": "gfs",
      "min": 0.5795276071142963,
      "max": 5.738583136731246,
      "mean": 2.948031626685374,
      "nan_reason": null
    },
    {
      "model": "aifs",
      "min": 2.2953063484251968,
      "max": 3.4648745078740157,
      "mean": 3.0555581844336768,
      "nan_reason": null
    }
  ]
}
```