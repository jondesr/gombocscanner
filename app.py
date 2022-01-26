from __future__ import annotations

from mangum import Mangum
import basicauth
from starlette import status
from starlette.applications import Starlette
from starlette.responses import Response
from starlette_graphene3 import GraphQLApp, make_graphiql_handler
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
import graphene
from src.queries import Query

class CustomHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        unauthenticated_response = Response("Incorrect email or password", status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})

        # Respond as unauthenticated when failing to parse header
        try:
            username, password = basicauth.decode(request.headers.get("authorization", ""))
        except Exception:
            return unauthenticated_response
        
        # Check username/password if successfully parsed
        if (not (username == "dev" and password == "uIES33LgtXTPObDu3RbM6sotDE70xGq7")):
            return unauthenticated_response

        response = await call_next(request)
        return response

middleware = [
    Middleware(CustomHeaderMiddleware),
    Middleware(CORSMiddleware, allow_origins=['*'])
]

app = Starlette(middleware=middleware)
schema = graphene.Schema(query=Query)

app.mount("/", GraphQLApp(schema, on_get=make_graphiql_handler()))  # Graphiql IDE

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

lambda_handler = Mangum(app)

if __name__ == "__main__":

    # Run as a local service (instead of having AWS Lambda invoke the "lambda_handler" method)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
    