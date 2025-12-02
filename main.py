import math
import ssl
import smtplib
from email.message import EmailMessage
from herbie import Herbie
import uvicorn
from fastapi import FastAPI
from datetime import datetime, timezone
import geopandas as gpd
import shapely
import os
import rioxarray as rxr
from rasterio.enums import Resampling
from rasterio.crs import CRS
from dotenv import load_dotenv
import numpy as np

from data_models import *


load_dotenv()


app = FastAPI()


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
            fcast=response,
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
    if hours <= 18:
        fxx = 18
    else:
        fxx = 48
    return ForecastFxx(fxx=fxx, hours=int(math.ceil(hours)))


async def _get_latest_herbie(model: str, valid_date: datetime) -> Herbie | None:
    """
    Get the latest Herbie object for the specified model.
    """
    for fxx in range(FXX[model] + 1):
        try:
            HL = Herbie(model=model, valid_date=valid_date, fxx=fxx, product=PRODUCT[model])
            if HL.grib:
                return HL
        except Exception as e:
            print(f"No model data yet")
    return None


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
    try:
        H = await _get_latest_herbie(model, valid_date.replace(tzinfo=None))
        inventory = H.inventory()
        if model in ["aifs", "ifs"]:
            asnow_search = f":(2t|{VARIABLE[model]}):sfc"
        elif model == "gfs":
            asnow_search = f":(TMP|{VARIABLE[model]}):surface"
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
        result = result.where(result != result.rio.nodata, drop=True)
        if model == "ifs":
            tF = 32 + result[1].data * C2F
            result = IPF(tF) * result[0].data * INCHES[model]
        elif model != "hrrr":
            tF = 32 + result[0].data * C2F
            tF[tF > 35] = np.nan
            result = IPF(tF) * result[1].data * INCHES[model]
        else:
            result = result.data * INCHES[model]
        H, ds, grib = None, None, None
        return ModelStats(model=model, min=np.nanmin(result), max=np.nanmax(result), mean=np.nanmean(result))
    except Exception as e:
        print(e)
        return ModelStats(model=model, nan_reason="No data")


async def _forecast_to_message(fcast: ForecastResponse) -> str:
    """
    Convert forecast data to a string message.
    """
    message = "Forecast Data:\n"
    for model in fcast.forecast:
        message += f"{model.model.upper()}: "
        if model.min:
            message += f"{model.min:.2f}/{model.max:.2f}/{model.mean:.2f}"
        else:
            message += "No data\n\n"
    return message


async def _email_forecast(account: EmailSMTP, subject: str, fcast: ForecastResponse, recipients: list[str]):
    context = ssl.create_default_context()
    forecast_message = await _forecast_to_message(fcast)
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
