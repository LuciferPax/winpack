import os
import json
import logging
from github import Github
from concurrent.futures import ThreadPoolExecutor
import click
import packaging.version

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

repo_url = "Bractothorpe/pkg"

def get_item(item, branch, repo):
    if item.type == 'blob':  # File
        content = repo.get_contents(item.path, ref=branch).decoded_content

        # Write the content to a file in the branch folder
        with open(f"packages/{branch}/{item.path}", "wb") as file:
            file.write(content)
            logger.info(f"Downloaded file: {item.path}")
    elif item.type == 'tree':  # Folder
        # Recursively get contents of the folder
        folder_contents = repo.get_contents(item.path, ref=branch)
        for content_item in folder_contents:
            get_item(content_item, branch, repo)

def install_dependencies(dependencies, branch):
    for dep in dependencies:
        dep_name = dep.get("name")
        dep_version = dep.get("version")
        if dep_name:
            logger.info(f"Resolving dependency: {dep_name}")
            local_path = f"packages/{dep_name}/pack.json"
            if not os.path.exists(local_path):
                logger.error(f"Dependency {dep_name} requires a pack.json file.")
                return False
            try:
                with open(local_path, "r") as file:
                    pack = json.load(file)
                    pack_version = pack.get('version')
                    if not pack_version:
                        logger.error(f"Dependency {dep_name} pack.json file does not contain a version number.")
                        return False
                    if dep_version:
                        dep_version_req = packaging.version.parse(dep_version)
                        if packaging.version.parse(pack_version) < dep_version_req:
                            logger.error(f"Dependency {dep_name} version {pack_version} does not satisfy required version {dep_version}")
                            return False
            except json.JSONDecodeError:
                logger.error(f"Error decoding pack.json for dependency {dep_name}.")
                return False
    return True

def get_package_meta(package):
    pack_json_path = f"packages/{package}/pack.json"
    if os.path.exists(pack_json_path):
        try:
            with open(pack_json_path, "r") as file:
                pack = json.load(file)
                version = pack.get('version', 'Unknown')
                description = pack.get('description', 'No description available')
                author = pack.get('name', 'Unknown')
                author_email = pack.get('author_email', 'None')
                dependencies = pack.get('dependencies', 'None')
                license = pack.get('license', 'Unknown')
                keywords = pack.get('keywords', 'None')
                homepage = pack.get('homepage', 'None')
                logger.info(f"Package: {package} Version: {version}")
                logger.info(f"Description: {description}")
                logger.info(f"Author: {author}")
                logger.info(f"Author Email: {author_email}")
                logger.info(f"Dependencies: {dependencies}")
                logger.info(f"License: {license}")
                logger.info(f"Keywords: {keywords}")
                logger.info(f"Homepage: {homepage}")
        except json.JSONDecodeError:
            logger.error(f"Error decoding pack.json for package {package}.")
    else:
        logger.error(f"Package {package} does not exist.")

def get_branch_contents(branch, resolved=None):
    if resolved is None:
        resolved = set()

    if branch in resolved:
        logger.info(f"Branch {branch} already resolved. Skipping.")
        return

    resolved.add(branch)
    g = Github()
    repo = g.get_repo(repo_url)
    repo_branch = repo.get_branch(branch)
    tree = repo.get_git_tree(repo_branch.commit.sha, recursive=True)

    if not os.path.exists("packages"):
        os.makedirs("packages")
    if not os.path.exists(f"packages/{branch}"):
        os.makedirs(f"packages/{branch}")

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(get_item, item, branch, repo) for item in tree.tree]
        for future in futures:
            future.result()

    try:
        with open(f"packages/{branch}/pack.json", "r") as file:
            pkg = json.load(file)
            dependencies = pkg.get("dependencies", [])
            if not install_dependencies(dependencies, branch):
                logger.error(f"Failed to install dependencies for {branch}.")
                return False
    except FileNotFoundError:
        logger.warning("No pack.json available in this branch. Skipping dependency check.")
    except json.JSONDecodeError:
        logger.error("Error decoding pack.json. Skipping dependency check.")
        return False

    return True

def update(branch_name):
    branch_path = f"packages/{branch_name}"
    if not os.path.exists(branch_path):
        logger.error(f"Branch {branch_name} does not exist.")
        return

    branch_json = f"{branch_path}/pack.json"
    if not os.path.exists(branch_json):
        logger.error(f"Branch {branch_name} does not contain a pack.json file.")
        return

    with open(branch_json, "r") as file:
        pack = json.load(file)
        if 'version' not in pack:
            logger.error(f"Branch {branch_name} does not contain a version number.")
            return

        local_version = pack['version']
        g = Github()
        repo = g.get_repo(repo_url)
        remote_branch = repo.get_branch(branch_name)
        tree = repo.get_git_tree(remote_branch.commit.sha, recursive=True)

        for item in tree.tree:
            if item.path == "pack.json":
                content = repo.get_contents(item.path, ref=branch_name).decoded_content
                remote_pack = json.loads(content)
                remote_version = remote_pack.get('version')

                if remote_version and packaging.version.parse(local_version) < packaging.version.parse(remote_version):
                    logger.info(f"Updating branch {branch_name} from {local_version} to {remote_version}")
                    get_branch_contents(branch_name)
                else:
                    logger.info(f"Branch {branch_name} is up to date.")
                return
        logger.error(f"Branch {branch_name} does not contain a valid pack.json file.")

def list_packages():
    for branch in os.listdir("packages"):
        try:
            with open(f"packages/{branch}/pack.json", "rb") as file:
                pkg = json.load(file)
                logger.info(f"Package: {branch} Version: {pkg.get('version', 'Unknown')}")
        except FileNotFoundError:
            logger.info(f"Package: {branch}")
            logger.warning("No pack.json available in this branch. Skipping.")
        except KeyError:
            logger.warning(f"No name or version found in pack.json. Skipping.")

def run_script(package):
  # open the folder in packages with the package name
  try:
    with open(f"packages/{package}/pack.json", "r") as file:
      pack = json.load(file)
      if "scripts" in pack:
        scripts = pack["scripts"]
        sorted_scripts = sorted(scripts.items(), key=lambda x: int(x[0]))
        for _, script in sorted_scripts:
          os.system(script)
      else:
        return 2 # no scripts to run
  except FileNotFoundError:
    logger.error(f"Package {package} does not exist.")
    return 0
  except json.JSONDecodeError:
    logger.error(f"Error decoding pack.json for package {package}.")
    return 0
  return 1

def uninstall(package):
  if os.path.exists(f"packages/{package}"):
    # recursively delete the folders contents and then the folder itself
    for root, dirs, files in os.walk(f"packages/{package}", topdown=False):
      for name in files:
        os.remove(os.path.join(root, name))
      for name in dirs:
        os.rmdir(os.path.join(root, name))
    os.rmdir(f"packages/{package}")
    logger.info(f"Successfully uninstalled package {package}.")
  else:
    logger.error(f"Package {package} does not exist.")

@click.group()
def cli():
    pass

@cli.command()
@click.argument('package')
def install(package):
    """Install the specified package."""
    if get_branch_contents(package):
        logger.info(f"Successfully installed package {package}.")
        if run_script(package) == 0:
          logger.error(f"Failed to run scripts for package {package}.")
          uninstall(package)
        elif run_script(package) == 1:
          logger.info(f"Successfully ran scripts for package {package}.")
    else:
      logger.error(f"Failed to install package {package}.")
      uninstall(package)

@cli.command()
@click.argument('package')
def info(package):
    """Get information about the specified package."""
    get_package_meta(package)

@cli.command()
@click.argument('branch_name')
def update(branch_name):
    """Update the specified branch."""
    update(branch_name)

@cli.command()
def list():
    """List all installed packages."""
    list_packages()

if __name__ == "__main__":
    cli()
