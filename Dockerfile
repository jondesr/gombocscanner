# This Dockerfile needs to run with the "--ssh default" argument
# docker build --ssh default .

FROM public.ecr.aws/lambda/python:3.8

# Download git client and trust the public key for github.com to enable private repo access
RUN yum install -y git
RUN mkdir -p -m 0600 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
# RUN --mount=type=ssh ssh -T git@github.com

# Python dependencies installation, with SSH host tunneling for private GitHub access
COPY requirements.txt ./
RUN --mount=type=ssh pip install -r requirements.txt -t .

# Embed the most recent fulfillment data, pulled into the dev environment by a VSCode task, but not committed to git.
COPY *.pkl ./
COPY *.py ./
COPY src ./src

# Command can be overwritten by providing a different command in the template directly.
CMD ["app.lambda_handler"]