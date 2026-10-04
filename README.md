# HomeSpace

## Run locally

Use Python 3.10 or newer. Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, set the local database and service credentials, then start the app with `python wsgi.py`. The app serves the frontend and API from the same Flask process.

## Deploy to PythonAnywhere

1. Create a PythonAnywhere account and a web app using the same Python version as the virtual environment. Python 3.10 or newer is required.
2. Open a Bash console and clone this repository into `/home/<your-username>/homespace` (or upload the project there). Do not upload the local `vhomespace` environment.
3. Create the virtual environment and install dependencies, replacing `3.13` with the version selected for the web app:

	```bash
	python3.13 -m venv ~/venvs/homespace
	source ~/venvs/homespace/bin/activate
	pip install -r ~/homespace/requirements.txt
	```

4. In the PythonAnywhere **Databases** tab, create a MySQL database and note its hostname, username, and database name. The hostname is normally `<your-username>.mysql.pythonanywhere-services.com`; database names are prefixed with your username.
5. Create `/home/<your-username>/homespace/.env` with production settings. Generate long random values for both secrets. Use the exact database hostname and database name shown in PythonAnywhere. URL-encode special characters in the database password before putting it in the connection URL.

	```dotenv
	FLASK_ENV=production
	SECRET_KEY=<long-random-secret>
	JWT_SECRET_KEY=<different-long-random-secret>
	DATABASE_URL=mysql+mysqlconnector://<db-user>:<url-encoded-password>@<db-host>/<db-name>
	CLOUDINARY_URL=cloudinary://<api-key>:<api-secret>@<cloud-name>
	PAYSTACK_SECRET_KEY=<paystack-secret-key>
	PAYSTACK_PUBLIC_KEY=<paystack-public-key>
	```

	`CLOUDINARY_URL` is needed for property image/video uploads. Paystack keys are needed for live payment flows. The chatbot currently returns a placeholder even when an Anthropic key is set because its API integration is not implemented yet. Keep `.env` private and never commit it.
6. In the **Web** tab, set the source code directory to `/home/<your-username>/homespace`, the virtualenv to `/home/<your-username>/venvs/homespace`, and edit the WSGI configuration file. Keep its generated imports/comments if desired, but set the project path and application as follows:

	```python
	import sys

	project_home = "/home/<your-username>/homespace"
	if project_home not in sys.path:
		 sys.path.insert(0, project_home)

	from wsgi import app as application
	```

	`wsgi.py` loads `.env` and defaults to the production configuration. Reload the web app after changing its WSGI file or `.env`.
7. In a Bash console, activate the virtualenv and apply the existing database migrations:

	```bash
	source ~/venvs/homespace/bin/activate
	cd ~/homespace
	flask --app wsgi:app db upgrade
	```

8. Reload the web app from the **Web** tab and open its PythonAnywhere URL. Check the web app error log there if startup fails.

The first deployment requires a PythonAnywhere MySQL database; the local MySQL URL in `.env.example` will not work on the hosted server. External payment and media uploads also require valid service credentials and outbound access from the PythonAnywhere account.
