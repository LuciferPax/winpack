import os
import tarfile
import logging
import json
from packaging import version
from packaging.specifiers import SpecifierSet
from github import Github
import requests

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

repo_url = "Bractothorpe/pkg"

def fetch_package(branch_name, expected_version=None, lockfile=None):
    try:
        # Create a Github instance
        g = Github()
        # Get the repository
        repo = g.get_repo(repo_url)
        
        # Get the branch and tree in one go
        branch = repo.get_branch(branch_name)
        tree = repo.get_git_tree(branch.commit.sha, recursive=True).tree
    except Exception as e:
        logging.error(f"Failed to create Github instance or get repository/branch/tree: {e}")
        return False

    try:
        # Create the directory for the branch
        os.makedirs(f"packages/{branch_name}", exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create directory for branch {branch_name}: {e}")
        return False

    package_json = None
    tarball_urls = []

    try:
        # Iterate over the files in the tree to find package.json and tarballs
        for item in tree:
            if item.path == "package.json":
                file_contents = repo.get_contents(item.path, ref=branch.commit.sha)
                package_json = json.loads(file_contents.decoded_content)
            elif item.path.endswith(".tar.gz"):
                tarball_urls.append(item.path)

        if package_json is None:
            logging.error("package.json not found")
            return False
    except Exception as e:
        logging.error(f"Failed to process package.json or tarballs: {e}")
        return False

    try:
        version_str = package_json.get("version")
        if expected_version is not None:
            if not version.parse(version_str) in SpecifierSet(expected_version):
                logging.error(f"Expected version {expected_version} but found {version_str}")
                return False
    except Exception as e:
        logging.error(f"Version check failed: {e}")
        return False

    if lockfile is None:
        lockfile = {"version": version_str, "dependencies": {}}

    try:
        # Check if dependencies are present
        if "dependencies" in package_json:
            dependencies = package_json.get("dependencies", {})
            for package_name, package_version in dependencies.items():
                logging.info(f"Resolving dependency {package_name}")
                if package_name not in lockfile["dependencies"]:
                    dependency_lockfile = {"version": None, "dependencies": {}}
                    if not fetch_package(package_name, package_version, dependency_lockfile):
                        logging.error(f"Failed to fetch dependency {package_name}")
                        return False
                    lockfile["dependencies"][package_name] = dependency_lockfile

        # Update the version of the current lockfile
        lockfile["version"] = version_str

    except Exception as e:
        logging.error(f"Failed to resolve dependencies: {e}")
        return False

    try:
        # Save the lockfile
        with open(f"packages/{branch_name}/package-lock.json", "w") as f:
            json.dump(lockfile, f)
    except Exception as e:
        logging.error(f"Failed to save package-lock.json: {e}")
        return False

    try:
        # Download and extract tarballs
        for tarball_path in tarball_urls:
            file_contents = repo.get_contents(tarball_path, ref=branch.commit.sha)
            tarball_url = file_contents.download_url
            response = requests.get(tarball_url, stream=True)
            local_tarball_path = os.path.join(f"packages/{branch_name}", os.path.basename(tarball_path))

            with open(local_tarball_path, 'wb') as tarball_file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        tarball_file.write(chunk)

            # Extract the tar.gz file
            with tarfile.open(local_tarball_path, mode="r:gz") as tar:
                tar.extractall(f"packages/{branch_name}", filter=None)

            # Delete the tar.gz file after extraction
            os.remove(local_tarball_path)
    except Exception as e:
        logging.error(f"Failed to download and extract tarball: {e}")
        return False

    return True

def uninstall_package(branch_name):
    try:
        for root, dirs, files in os.walk(f"packages/{branch_name}", topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(f"packages/{branch_name}")
    except Exception as e:
        logging.error(f"Failed to uninstall package {branch_name}: {e}")
        return False
    return True

def install_package(branch_name):
    if not fetch_package(branch_name):
        logging.error(f"Failed to fetch package {branch_name}")
        uninstall_package(branch_name)
        return False
    logging.info(f"Successfully installed package {branch_name}")
    return True

def update_package(branch_name):
  # get the package in the repository
  g = Github()
  repo = g.get_repo(repo_url)
  branch = repo.get_branch(branch_name)

  tree = repo.get_git_tree(branch.commit.sha, recursive=True).tree
  package_json = None
  try:
    for item in tree:
      if item.path == "package.json":
        file_contents = repo.get_contents(item.path, ref=branch.commit.sha)
        package_json = json.loads(file_contents.decoded_content)

        with open(f"packages/{branch_name}/package-lock.json", "r") as f:
          lockfile = json.load(f)
          # check if the version is different
          if package_json.get("version") > lockfile.get("version"):
            uninstall_package(branch_name)
            install_package(branch_name)
            return True
          else:
            logging.info(f"Package {branch_name} is already up to date")
            return False
  except Exception as e:
    logging.error(f"Failed to update package {branch_name}: {e}")
    return False
      

# Example usage
install_package("test")
