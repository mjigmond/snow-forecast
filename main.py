import math
import ssl
import smtplib
from email.message import EmailMessage
from typing import Literal, Self
from herbie import Herbie, HerbieLatest
import uvicorn
from fastapi import FastAPI
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator
import geopandas as gpd
import shapely
import os
import rioxarray as rxr
from rasterio.enums import Resampling
from rasterio.crs import CRS
from dotenv import load_dotenv


load_dotenv()


INCHES = {  # Conversion factor from model units to inches
    "hrrr": 3.28084 * 12,
    "gfs": 10 / 25.4,
    "aifs": 10 / 25.4,
}
VALID_MODELS = ["hrrr", "gfs", "aifs"]
PRODUCT = {
    "hrrr": "sfc",
    "gfs": "pgrb2.0p25",
    "aifs": "oper",
}
VARIABLE = {
    "hrrr": "ASNOW",
    "gfs": "WEASD",
    "aifs": "sf",
}
RESOLUTION = {
    "hrrr": 300,
    "gfs": .01,
    "aifs": .01,
}
PROVIDER_DOMAINS = {
    'verizon': 'mypixmessages.com',
    'at&t': 'mms.att.net',
    't-mobile': 'tmomail.net'
}


app = FastAPI()

class EmailSMTP(BaseModel):
    server: str = "smtp.gmail.com"
    user: str
    password: str


class Recipient(BaseModel):
    number: int = Field(gt=999999999, le=9999999999, description="Recipient's phone number")
    network: Literal["verizon", "at&t", "t-mobile"]


class ForecastFxx(BaseModel):
    fxx: int
    hours: int


class ModelStats(BaseModel):
    model: str
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    nan_reason: str | None = None


class ForecastResponse(BaseModel):
    name: str
    attime: str
    forecast: list[ModelStats]


class ForecastRequest(BaseModel):
    name: str
    attime: str
    models: list[str]
    lat: float | None = None
    lon: float | None = None
    geometry: str | None = None
    recipients: list[Recipient] | None = None

    @model_validator(mode="after")
    def check_input(self) -> Self:
        if self.lat and self.lon and self.geometry:
            raise ValueError("Either lat/lon or geometry must be provided, not both.")
        if (self.lat and not self.lon) or (self.lon and not self.lat):
            raise ValueError("Both lat and lon must be provided.")
        if not self.geometry and not self.lat and not self.lon:
            raise ValueError("One of lat/lon or geometry must be provided.")
        if set(self.models).intersection(set(VALID_MODELS)) != set(self.models):
            raise ValueError(f"Models must be from {VALID_MODELS}.")
        return self


@app.post("/forecast")
async def forecast(request: ForecastRequest) -> ForecastResponse:
    """
    Get forecast data for a given ForecastRequest.
    """
    valid_date = datetime.fromisoformat(request.attime).astimezone(timezone.utc)
    results = []
    for model in request.models:
        if model not in VALID_MODELS:
            raise ValueError(f"Model {model} is not valid. Must be one of {VALID_MODELS}.")
        results.append(await _process_model(
            model=model,
            valid_date=valid_date,
            wkt=request.geometry,
            lat=request.lat,
            lon=request.lon
        ))
    response = ForecastResponse(name=request.name, attime=request.attime, forecast=results)
    if request.recipients:
        recipients = [f"{r.number}@{PROVIDER_DOMAINS[r.network]}" for r in request.recipients]
        await _email_forecast(
            account=EmailSMTP(user=os.environ.get('EMAIL_USER'), password=os.environ.get('EMAIL_PASS')),
            subject=f"Forecast for {request.name} @ {request.attime}",
            forecast=response,
            recipients=recipients
        )
    return response


async def _get_fxx(attime: datetime) -> ForecastFxx:
    """
    Get the forecast period (fxx) based on the provided attime.
    """
    now = datetime.now(timezone.utc)
    if attime < now:
        raise ValueError("attime must be in the future")
    hours = (attime - now).total_seconds() / 3600
    # if hours > 48:
    #     raise ValueError("attime must be within 48 hours")
    if hours <= 18:
        fxx = 18
    else:
        fxx = 48
    return ForecastFxx(fxx=fxx, hours=int(math.floor(hours)))


async def _get_latest_herbie(model: str, fxx: int) -> HerbieLatest:
    """
    Get the latest Herbie object for the specified model.
    """
    try:
        HL = HerbieLatest(model=model, fxx=fxx, product=PRODUCT[model], periods=10)
    except TimeoutError as e:
        print(f"TimeoutError: {e}")
        raise
    return HL


async def _get_geometry(wkt: str, crs: CRS):
    """
    Convert WKT string to GeoDataFrame.
    """
    try:
        geom = shapely.from_wkt(wkt)
        if not geom.is_valid:
            raise ValueError("Invalid geometry")
    except Exception as e:
        raise ValueError(f"Invalid WKT geometry: {e}")
    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    return gdf.to_crs(crs)


async def _process_model(
        model: str, valid_date: datetime,
        wkt: str | None = None, lat: float | None = None, lon: float | None = None
        ) -> ModelStats:
    """
    Process the model data and return statistics.
    """

    ffxx = await _get_fxx(valid_date)
    try:
        HL = await _get_latest_herbie(model, ffxx.fxx)

        # compute new fxx based on latest available data
        fxx = ffxx.fxx - (HL.valid_date.tz_localize(timezone.utc) - valid_date).total_seconds() / 3600
        H = Herbie(date=HL.date, model=model, fxx=int(fxx), product=PRODUCT[model])
        inventory = H.inventory()
        if model == "aifs":
            asnow_search = inventory[inventory.param == VARIABLE[model]].search_this.values[0]
        else:
            asnow_search = inventory[inventory.variable == VARIABLE[model]].search_this.values[0]
        grib = H.download(asnow_search, verbose=True)
        ds = rxr.open_rasterio(grib, decode_times=False)
        if not wkt:
            wkt = f"POINT({lon} {lat})"
        gdf = await _get_geometry(wkt, ds.rio.crs)
        ds = ds.rio.clip(gdf.geometry.values, all_touched=True)
        ds = ds.rio.reproject(ds.rio.crs, resolution=RESOLUTION[model], resampling=Resampling.nearest)
        if gdf.geometry[0].geom_type == 'Polygon':
            result = ds.rio.clip(gdf.geometry.values, drop=True)
        else:
            result = ds.sel(x=gdf.geometry.x.values, y=gdf.geometry.y.values, method="nearest")
        result = result.where(result != result.rio.nodata, drop=True) * INCHES[model]
        HL, H, ds, grib = None, None, None, None
        return ModelStats(model=model, min=result.min().item(), max=result.max().item(), mean=result.mean().item())
    except Exception as e:
        print(e)
        return ModelStats(model=model, nan_reason="No data")


async def _forecast_to_message(forecast: ForecastResponse) -> str:
    """
    Convert forecast data to a string message.
    """
    message = "Forecast Data:\n"
    for model in forecast.forecast:
        message += f"Model: {model.model.upper()}\n"
        if model.min:
            message += f"Min: {model.min:.2f}\n"
            message += f"Max: {model.max:.2f}\n"
            message += f"Mean: {model.mean:.2f}\n\n"
        else:
            message += "No data\n\n"
    return message


async def _email_forecast(account: EmailSMTP, subject: str, forecast: ForecastResponse, recipients: list[str]):
    context = ssl.create_default_context()
    forecast_message = await _forecast_to_message(forecast)
    with smtplib.SMTP(account.server, 587) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(account.user, account.password)

        msg = EmailMessage()
        msg['From'] = account.user
        msg['To'] = ','.join(recipients)
        msg['Subject'] = subject
        msg.set_content(forecast_message)
        smtp.send_message(msg)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)
